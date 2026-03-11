# ==============================================================================
# Pixel Canvas — Makefile
# Usage: make <target>   |   make help
# ==============================================================================

STACK_NAME   ?= pixel-canvas-stack
REGION       ?= eu-west-3
FRONTEND_DIR  = frontend

# Resolved from stack outputs at runtime (used by redeploy-redirect and frontend-deploy)
REST_API_URL  = $(shell aws cloudformation describe-stacks \
                  --stack-name $(STACK_NAME) --region $(REGION) \
                  --query "Stacks[0].Outputs[?OutputKey=='RestApiURL'].OutputValue" \
                  --output text 2>/dev/null)

.DEFAULT_GOAL := help
.PHONY: help \
        secrets-discord secrets-app secrets secrets-check \
        validate build deploy deploy-guided redeploy redeploy-redirect outputs \
        frontend-install frontend-env frontend-build frontend-deploy frontend \
        all rollback teardown

# ------------------------------------------------------------------------------
# Help
# ------------------------------------------------------------------------------
help:
	@echo ""
	@echo "  Pixel Canvas — available targets"
	@echo ""
	@echo "  Secrets (run once before first deploy)"
	@echo "    make secrets-discord   Create DiscordSecrets in Secrets Manager"
	@echo "    make secrets-app       Create AppSecrets in Secrets Manager"
	@echo "    make secrets           Both of the above"
	@echo "    make secrets-check     Verify secrets exist before deploying"
	@echo ""
	@echo "  Backend (SAM)"
	@echo "    make validate          Lint the SAM template"
	@echo "    make build             sam build"
	@echo "    make deploy-guided     First deploy — interactive wizard (saves samconfig.toml)"
	@echo "    make deploy            Re-deploy using saved samconfig.toml"
	@echo "    make redeploy          build + deploy in one shot"
	@echo "    make redeploy-redirect Patch OAuthRedirectUri after first deploy"
	@echo "    make outputs           Print the stack outputs"
	@echo ""
	@echo "  Frontend (Svelte)"
	@echo "    make frontend-install  npm install"
	@echo "    make frontend-env      Write frontend/.env from live stack outputs"
	@echo "    make frontend-build    npm run build"
	@echo "    make frontend-deploy   Sync dist/ to the S3 bucket"
	@echo "    make frontend          install → env → build → deploy"
	@echo ""
	@echo "  Full flow"
	@echo "    make all               redeploy + frontend (assumes secrets exist)"
	@echo ""
	@echo "  Cleanup / Recovery"
	@echo "    make rollback          Roll back a stuck CREATE_FAILED stack"
	@echo "    make teardown          Delete the CloudFormation stack"
	@echo ""
	@echo "  Config  (override with: make <target> STACK_NAME=my-stack REGION=eu-west-1)"
	@echo "    STACK_NAME = $(STACK_NAME)"
	@echo "    REGION     = $(REGION)"
	@echo ""

# ------------------------------------------------------------------------------
# Phase 1 — Secrets
# ------------------------------------------------------------------------------
secrets-discord:
	@echo "Upserting DiscordSecrets in Secrets Manager (region: $(REGION))..."
	@read -p "  ClientId:     " cid; \
	 read -p "  ClientSecret: " csec; \
	 read -p "  PublicKey:    " pub; \
	 read -p "  AppId:        " app; \
	 PAYLOAD="{\"ClientId\":\"$$cid\",\"ClientSecret\":\"$$csec\",\"PublicKey\":\"$$pub\",\"AppId\":\"$$app\"}"; \
	 if aws secretsmanager describe-secret --secret-id DiscordSecrets --region $(REGION) > /dev/null 2>&1; then \
	   echo "  Secret exists — updating value..."; \
	   aws secretsmanager put-secret-value \
	     --secret-id DiscordSecrets \
	     --region $(REGION) \
	     --secret-string "$$PAYLOAD"; \
	 else \
	   aws secretsmanager create-secret \
	     --name DiscordSecrets \
	     --region $(REGION) \
	     --secret-string "$$PAYLOAD"; \
	 fi
	@echo "DiscordSecrets ready in $(REGION)."

secrets-app:
	@echo "Upserting AppSecrets in Secrets Manager (region: $(REGION))..."
	@read -p "  JwtSecret (leave blank to auto-generate): " jwt; \
	 if [ -z "$$jwt" ]; then jwt=$$(openssl rand -hex 32); echo "  Generated: $$jwt"; fi; \
	 PAYLOAD="{\"JwtSecret\":\"$$jwt\"}"; \
	 if aws secretsmanager describe-secret --secret-id AppSecrets --region $(REGION) > /dev/null 2>&1; then \
	   echo "  Secret exists — updating value..."; \
	   aws secretsmanager put-secret-value \
	     --secret-id AppSecrets \
	     --region $(REGION) \
	     --secret-string "$$PAYLOAD"; \
	 else \
	   aws secretsmanager create-secret \
	     --name AppSecrets \
	     --region $(REGION) \
	     --secret-string "$$PAYLOAD"; \
	 fi
	@echo "AppSecrets ready in $(REGION)."

secrets: secrets-discord secrets-app

secrets-check:
	@echo "Checking required secrets exist in $(REGION)..."
	@aws secretsmanager describe-secret --secret-id DiscordSecrets --region $(REGION) > /dev/null 2>&1 || \
	  { echo "  ERROR: 'DiscordSecrets' not found in $(REGION). Run: make secrets-discord REGION=$(REGION)"; exit 1; }
	@aws secretsmanager describe-secret --secret-id AppSecrets --region $(REGION) > /dev/null 2>&1 || \
	  { echo "  ERROR: 'AppSecrets' not found in $(REGION). Run: make secrets-app REGION=$(REGION)"; exit 1; }
	@echo "  OK — both secrets found in $(REGION)."

# ------------------------------------------------------------------------------
# Phase 2 — Backend
# ------------------------------------------------------------------------------
validate:
	sam validate --lint

build:
	sam build

deploy-guided: build
	sam deploy --guided --region $(REGION) --stack-name $(STACK_NAME)

deploy:
	sam deploy --region $(REGION) --stack-name $(STACK_NAME)

redeploy: build deploy

redeploy-redirect:
	@$(eval REDIRECT := $(REST_API_URL)/auth/callback)
	@if [ -z "$(REST_API_URL)" ]; then \
	  echo "Error: could not resolve RestApiURL from stack '$(STACK_NAME)'. Has it been deployed?"; exit 1; \
	fi
	@echo "Patching OAuthRedirectUri → $(REDIRECT)"
	sam deploy \
	  --region $(REGION) \
	  --stack-name $(STACK_NAME) \
	  --parameter-overrides OAuthRedirectUri="$(REDIRECT)" \
	  --no-confirm-changeset

outputs:
	@aws cloudformation describe-stacks \
	  --stack-name $(STACK_NAME) \
	  --region $(REGION) \
	  --query "Stacks[0].Outputs[].[OutputKey,OutputValue]" \
	  --output table

# ------------------------------------------------------------------------------
# Phase 4 — Frontend
# ------------------------------------------------------------------------------
frontend-install:
	cd $(FRONTEND_DIR) && npm install

frontend-env:
	@$(eval WSS_URL := $(shell aws cloudformation describe-stacks \
	  --stack-name $(STACK_NAME) --region $(REGION) \
	  --query "Stacks[0].Outputs[?OutputKey=='WebSocketURL'].OutputValue" \
	  --output text 2>/dev/null))
	@if [ -z "$(REST_API_URL)" ] || [ -z "$(WSS_URL)" ]; then \
	  echo "Error: could not resolve stack outputs. Run 'make outputs' to check."; exit 1; \
	fi
	@echo "Writing $(FRONTEND_DIR)/.env..."
	@printf "VITE_API_URL=$(REST_API_URL)\nVITE_WSS_URL=$(WSS_URL)\n" > $(FRONTEND_DIR)/.env
	@echo "  VITE_API_URL=$(REST_API_URL)"
	@echo "  VITE_WSS_URL=$(WSS_URL)"

frontend-build:
	cd $(FRONTEND_DIR) && npm run build

frontend-deploy: frontend-build
	@echo "🔍 Locating frontend bucket for stack: $(STACK_NAME)..."
	$(eval BUCKET_NAME=$(shell aws cloudformation describe-stack-resource \
		--stack-name $(STACK_NAME) \
		--logical-resource-id FrontendBucket \
		--query "StackResourceDetail.PhysicalResourceId" \
		--output text --region $(REGION) 2>/dev/null))

	@if [ -z "$(BUCKET_NAME)" ] || [ "$(BUCKET_NAME)" = "None" ]; then \
		echo "❌ Error: Could not find PhysicalResourceId for 'FrontendBucket' in stack '$(STACK_NAME)'."; \
		exit 1; \
	fi

	@echo "Syncing $(FRONTEND_DIR)/dist/ → s3://$(BUCKET_NAME)"
	aws s3 sync $(FRONTEND_DIR)/dist/ s3://$(BUCKET_NAME) --delete --region $(REGION)

	@echo "Invalidation CloudFront cache (optional but recommended)..."
	$(eval DIST_ID=$(shell aws cloudformation describe-stack-resource \
		--stack-name $(STACK_NAME) \
		--logical-resource-id FrontendDistribution \
		--query "StackResourceDetail.PhysicalResourceId" \
		--output text --region $(REGION) 2>/dev/null))
	@if [ ! -z "$(DIST_ID)" ] && [ "$(DIST_ID)" != "None" ]; then \
		aws cloudfront create-invalidation --distribution-id $(DIST_ID) --paths "/*" --region $(REGION) > /dev/null; \
		echo "Successfully triggered CloudFront invalidation: $(DIST_ID)"; \
	fi

frontend: frontend-install frontend-env frontend-deploy

# ------------------------------------------------------------------------------
# Phase 5 — Discord Commands
# ------------------------------------------------------------------------------
discord-commands:
	@echo "Registering Discord commands..."
	python script/register_commands.py

uv-discord-commands:
	@echo "Registering Discord commands using uv..."
	uv run python script/register_commands.py
# ------------------------------------------------------------------------------
# Full flow
# ------------------------------------------------------------------------------
all: redeploy frontend

# ------------------------------------------------------------------------------
# Cleanup / Recovery
# ------------------------------------------------------------------------------
rollback:
	@echo "Rolling back stack '$(STACK_NAME)' to last stable state..."
	aws cloudformation rollback-stack --stack-name $(STACK_NAME) --region $(REGION)
	@echo "Rollback initiated. Monitor: aws cloudformation describe-stacks --stack-name $(STACK_NAME) --region $(REGION)"

teardown:
	@read -p "Delete stack '$(STACK_NAME)' in $(REGION)? This is irreversible. [y/N] " confirm; \
	 if [ "$$confirm" = "y" ] || [ "$$confirm" = "Y" ]; then \
	   aws cloudformation delete-stack --stack-name $(STACK_NAME) --region $(REGION); \
	   echo "Deletion initiated. Monitor progress in the CloudFormation console."; \
	 else \
	   echo "Aborted."; \
	 fi
