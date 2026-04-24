PYTHON       ?= python3
VENV         ?= .venv
VPY          := $(VENV)/bin/python
VPIP         := $(VENV)/bin/pip
APP_NAME     := macOS-HL7
APP_BUNDLE   := dist/$(APP_NAME).app

.PHONY: all venv install install-build run build install-app clean nuke

all: run

$(VPY):
	$(PYTHON) -m venv $(VENV)
	$(VPIP) install --upgrade pip wheel setuptools

venv: $(VPY)

install: venv
	$(VPIP) install -r requirements.txt

install-build: venv
	$(VPIP) install -r requirements-build.txt

run: install
	$(VPY) -m app

build: install-build
	rm -rf build dist
	$(VPY) setup.py py2app

install-app: build
	rm -rf /Applications/$(APP_NAME).app
	cp -R $(APP_BUNDLE) /Applications/
	@echo "Installed: /Applications/$(APP_NAME).app"

clean:
	rm -rf build dist

nuke: clean
	rm -rf $(VENV)
