.PHONY: setup run start stop test backtest check status install-service clean help

VENV = .venv
PYTHON = $(VENV)/bin/python
PIP = $(VENV)/bin/pip

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

setup: ## Set up the project (venv, deps, config)
	@echo "Setting up StockPulse..."
	@test -d $(VENV) || uv venv $(VENV)
	@$(VENV)/bin/uv pip install -e ".[dev]" 2>/dev/null || $(PIP) install -e ".[dev]"
	@test -f .env || cp .env.example .env
	@mkdir -p outputs/{reports,json,logs}
	@echo ""
	@echo "Setup complete! Next steps:"
	@echo "  1. Get a free API key at https://finnhub.io"
	@echo "  2. Edit .env and set FINNHUB_API_KEY=your_key"
	@echo "  3. Run 'make check' to validate your setup"
	@echo "  4. Run 'make run' for a one-shot scan"

run: ## Run a one-shot scan
	@$(PYTHON) run.py scan

start: ## Start the scheduler (background scanning)
	@$(PYTHON) run.py schedule

stop: ## Stop the scheduler service
	@systemctl --user stop stockpulse 2>/dev/null || echo "Service not running"

test: ## Run the test suite
	@$(PYTHON) -m pytest tests/ -v

backtest: ## Run a backtest (default: last 6 months)
	@$(PYTHON) run.py backtest --start $$(date -d '-6 months' +%Y-%m-%d) --end $$(date +%Y-%m-%d)

check: ## Validate your setup (API keys, connections)
	@$(PYTHON) -m stockpulse.utils.validate_setup

status: ## Show scheduler and service status
	@systemctl --user status stockpulse 2>/dev/null || echo "Service not installed. Run 'make install-service'"

install-service: ## Install as a systemd user service (auto-start on boot)
	@mkdir -p ~/.config/systemd/user
	@echo "[Unit]" > ~/.config/systemd/user/stockpulse.service
	@echo "Description=StockPulse Stock Research & Alert System" >> ~/.config/systemd/user/stockpulse.service
	@echo "After=network-online.target" >> ~/.config/systemd/user/stockpulse.service
	@echo "Wants=network-online.target" >> ~/.config/systemd/user/stockpulse.service
	@echo "" >> ~/.config/systemd/user/stockpulse.service
	@echo "[Service]" >> ~/.config/systemd/user/stockpulse.service
	@echo "Type=simple" >> ~/.config/systemd/user/stockpulse.service
	@echo "WorkingDirectory=$$(pwd)" >> ~/.config/systemd/user/stockpulse.service
	@echo "ExecStart=$$(pwd)/$(VENV)/bin/python run.py schedule" >> ~/.config/systemd/user/stockpulse.service
	@echo "Restart=on-failure" >> ~/.config/systemd/user/stockpulse.service
	@echo "RestartSec=30" >> ~/.config/systemd/user/stockpulse.service
	@echo "EnvironmentFile=$$(pwd)/.env" >> ~/.config/systemd/user/stockpulse.service
	@echo "" >> ~/.config/systemd/user/stockpulse.service
	@echo "[Install]" >> ~/.config/systemd/user/stockpulse.service
	@echo "WantedBy=default.target" >> ~/.config/systemd/user/stockpulse.service
	@systemctl --user daemon-reload
	@systemctl --user enable stockpulse
	@loginctl enable-linger $$(whoami) 2>/dev/null || true
	@echo "Service installed. Run 'make start' or 'systemctl --user start stockpulse'"

clean: ## Remove outputs, cache, and generated files
	@rm -rf outputs/reports/* outputs/json/* outputs/logs/* outputs/.cache 2>/dev/null
	@echo '{"signals": [], "stats": {}, "validation": {}}' > outputs/.signal_tracker.json
	@test -f outputs/.portfolio_state.json || echo '{"alerted_milestones": {}}' > outputs/.portfolio_state.json
	@echo '{}' > outputs/.score_history.json
	@echo "Cleaned all outputs"

enter: ## Enter a position (usage: make enter TICKER=GOOGL SHARES=10)
	@$(PYTHON) run.py enter --ticker $(TICKER) $(if $(SHARES),--shares $(SHARES),)
