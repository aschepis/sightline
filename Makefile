### CONFIG ####################################################################

CONDA_ENV := sightline-build
CONDA_PY := 3.12
APP := Sightline
SPEC := sightline.spec
DIST_APP := dist/$(APP).app
SIGNING_IDENTITY ?= -

### INTERNAL ##################################################################

# Helper to run commands inside the conda environment
CONDA_RUN := conda run -n $(CONDA_ENV)

### TARGETS ###################################################################

.PHONY: help conda-env conda-remove install install-dev build build-windows build-macos sign \
        notarize create-dmg create-windows-installer dist-macos dist clean shell test lint format check run \
        check-deps

help:
	@echo "Conda-based build system for macOS Sightline.app"
	@echo ""
	@echo "Available targets:"
	@echo "  make conda-env       Create the conda environment"
	@echo "  make install         Install runtime dependencies"
	@echo "  make install-dev     Install dev dependencies + pyinstaller"
	@echo "  make test            Run tests with coverage"
	@echo "  make lint            Run linting checks (flake8, black, isort, mypy)"
	@echo "  make format          Auto-format code with black and isort"
	@echo "  make check           Run tests and linting (fails on any error)"
	@echo "  make build-windows   Build Windows executable (dist/Sightline/)"
	@echo "  make build-macos     Build macOS .app bundle"
	@echo "  make sign            Sign the .app (use SIGNING_IDENTITY=<id> for real signing)"
	@echo "  make notarize        Notarize the signed .app (requires APPLE_ID, APPLE_TEAM_ID)"
	@echo "  make create-dmg      Create DMG from signed .app (use VERSION=x.x.x)"
	@echo "  make create-windows-installer Create Windows installer (use VERSION=x.x.x)"
	@echo "  make dist-macos      Build, sign, notarize, and create DMG (full release)"
	@echo "  make dist            Create distributable .zip"
	@echo "  make shell           Enter the conda env shell"
	@echo "  make clean           Remove build output"
	@echo "  make conda-remove    Remove the conda env entirely"
	@echo ""
	@echo "Examples:"
	@echo "  make sign                                    # Ad-hoc signing (for local testing)"
	@echo "  make sign SIGNING_IDENTITY='Developer ID'   # Sign with Apple Developer ID"
	@echo "  make create-dmg VERSION=1.2.3                # Create DMG with version number"
	@echo "  make dist-macos VERSION=1.2.3 SIGNING_IDENTITY='Developer ID' # Full release"

### ENVIRONMENT MANAGEMENT ####################################################

conda-env:
	conda create -y -n $(CONDA_ENV) python=$(CONDA_PY)

conda-remove:
	conda remove -y --name $(CONDA_ENV) --all

shell:
	conda run -n $(CONDA_ENV) bash

### INSTALLATION ##############################################################

install:
	$(CONDA_RUN) pip install --upgrade pip
	$(CONDA_RUN) pip install -r requirements.txt

install-dev: install
	$(CONDA_RUN) pip install -r requirements-dev.txt
	$(CONDA_RUN) pip install pyinstaller

### TESTING ###################################################################

test:
	$(CONDA_RUN) pytest tests/ -v

run:
	$(CONDA_RUN) python main.py --log-file=sightline.log

### DEPENDENCY CHECKING #######################################################

check-deps:
	@scripts/check-deps.sh $(CONDA_ENV)

### CODE QUALITY ###############################################################

lint:
	@echo "→ Running flake8..."
	$(CONDA_RUN) flake8 main.py tests/
	@echo "→ Running black (check mode)..."
	$(CONDA_RUN) black --check main.py tests/
	@echo "→ Running isort (check mode)..."
	$(CONDA_RUN) isort --check-only main.py tests/
	@echo "→ Running mypy..."
	$(CONDA_RUN) mypy main.py
	@echo "✓ All linting checks passed!"

format:
	@echo "→ Running black..."
	$(CONDA_RUN) black main.py tests/
	@echo "→ Running isort..."
	$(CONDA_RUN) isort main.py tests/
	@echo "✓ Code formatted!"

check: test lint
	@echo ""
	@echo "✓ All checks passed!"

### BUILDING ##################################################################

build: build-macos

build-windows:
	$(CONDA_RUN) bash scripts/pyinstaller-without-conda.sh "$(SPEC)"
	@echo "Build complete! Output is in dist/Sightline/"

build-macos:
	$(CONDA_RUN) bash scripts/pyinstaller-without-conda.sh "$(SPEC)"
	@echo "→ Post-processing: Moving Tcl/Tk libraries to lib directory..."
	@if [ -d "$(DIST_APP)/Contents/Resources/tcl" ]; then \
		mkdir -p $(DIST_APP)/Contents/lib; \
		if [ -d "$(DIST_APP)/Contents/lib/tcl8.6" ]; then \
			rm -rf $(DIST_APP)/Contents/lib/tcl8.6; \
		fi; \
		mv $(DIST_APP)/Contents/Resources/tcl $(DIST_APP)/Contents/lib/tcl8.6; \
		echo "  ✓ Moved Tcl library to Contents/lib/tcl8.6"; \
	fi
	@if [ -d "$(DIST_APP)/Contents/Resources/tk" ]; then \
		mkdir -p $(DIST_APP)/Contents/lib; \
		if [ -d "$(DIST_APP)/Contents/lib/tk8.6" ]; then \
			rm -rf $(DIST_APP)/Contents/lib/tk8.6; \
		fi; \
		mv $(DIST_APP)/Contents/Resources/tk $(DIST_APP)/Contents/lib/tk8.6; \
		echo "  ✓ Moved Tk library to Contents/lib/tk8.6"; \
	fi
	@echo "→ Post-processing: Removing invalid symlinks..."
	@if [ -L "$(DIST_APP)/Contents/Frameworks/tk" ]; then \
		rm -f $(DIST_APP)/Contents/Frameworks/tk; \
		echo "  ✓ Removed invalid tk symlink from Frameworks"; \
	fi
	@if [ -L "$(DIST_APP)/Contents/Frameworks/tcl" ]; then \
		rm -f $(DIST_APP)/Contents/Frameworks/tcl; \
		echo "  ✓ Removed invalid tcl symlink from Frameworks"; \
	fi
	@echo "✓ Post-processing complete!"

### SIGNING ###################################################################

sign:
	@scripts/sign-app.sh "$(DIST_APP)" "$(SIGNING_IDENTITY)" "$(APP)"

notarize:
	@echo "→ Notarizing $(DIST_APP)..."
	@if [ -z "$(APPLE_ID)" ] || [ -z "$(APPLE_TEAM_ID)" ]; then \
		echo "Error: APPLE_ID and APPLE_TEAM_ID environment variables must be set"; \
		exit 1; \
	fi
	ditto -c -k --keepParent $(DIST_APP) $(DIST_APP).zip
	xcrun notarytool submit $(DIST_APP).zip \
		--apple-id "$(APPLE_ID)" \
		--team-id "$(APPLE_TEAM_ID)" \
		--password "$(APPLE_APP_SPECIFIC_PASSWORD)" \
		--wait
	xcrun stapler staple $(DIST_APP)
	rm $(DIST_APP).zip
	@echo "✓ Notarization complete!"

### PACKAGING #################################################################

create-dmg:
	@echo "→ Creating DMG..."
	@if [ -z "$(VERSION)" ]; then \
		VERSION="1.0.0"; \
		echo "Warning: VERSION not set, using default: $$VERSION"; \
	fi
	mkdir -p dist-packages
	hdiutil create -volname "$(APP)" \
		-srcfolder $(DIST_APP) \
		-ov -format UDZO \
		"dist-packages/$(APP)-$${VERSION}-macOS.dmg"
	@echo "✓ DMG created: dist-packages/$(APP)-$${VERSION}-macOS.dmg"

create-windows-installer:
	@powershell.exe -ExecutionPolicy Bypass -File scripts/create-windows-installer.ps1 -Version "$(VERSION)" -AppName "$(APP)"

dist-macos: build-macos sign notarize create-dmg
	@echo "✓ Complete macOS distribution package created!"

dist:
	mkdir -p dist-packages
	cd dist && zip -r ../dist-packages/$(APP)-macos.zip $(APP).app
	@echo "→ Distribution package: dist-packages/$(APP)-macos.zip"

### CLEANUP ###################################################################

clean:
	$(CONDA_RUN) python -c "import shutil, pathlib; shutil.rmtree('build', ignore_errors=True); shutil.rmtree('dist', ignore_errors=True); shutil.rmtree('__pycache__', ignore_errors=True); [shutil.rmtree(str(p), ignore_errors=True) for p in pathlib.Path('.').rglob('__pycache__')]; [shutil.rmtree(str(p), ignore_errors=True) for p in pathlib.Path('.').glob('*.egg-info')]"
	@echo "Clean complete!"
