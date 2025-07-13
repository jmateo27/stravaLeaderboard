.PHONY: venv

VENV_DIR := venv
VENV_PY := $(VENV_DIR)/Scripts/python
VENV_PIP := $(VENV_DIR)/Scripts/pip
REQUIRED_PACKAGES := flask requests stravalib qrcode[pil]

venv:
	@if [ ! -d "$(VENV_DIR)" ]; then \
		echo "Creating virtual environment..."; \
		python3 -m venv $(VENV_DIR); \
	else \
		echo "Virtual environment already exists. Skipping creation."; \
	fi

	@echo "Activating virtual environment and checking packages..."
	@. $(VENV_DIR)/Scripts/activate && \
	for pkg in $(REQUIRED_PACKAGES); do \
		base=$$(echo $$pkg | cut -d'[' -f1); \
		if ! $(VENV_PIP) show $$base > /dev/null 2>&1; then \
			echo "Installing $$pkg..."; \
			$(VENV_PIP) install "$$pkg"; \
		else \
			echo "$$pkg already installed."; \
		fi; \
	done

	@echo ""
	@echo "Done. To activate your virtual environment, run:"
	@echo "   source venv/Scripts/activate"
