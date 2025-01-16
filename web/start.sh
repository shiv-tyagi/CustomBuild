#!/bin/sh

# Ensure base subdirectories exist
mkdir -p "$CBS_BASEDIR/builds" "$CBS_BASEDIR/configs"

# Ensure status.json exist
STATUS_JSON_PATH="$CBS_BASEDIR/builds/status.json"
if ! [ -f "$STATUS_JSON_PATH" ]; then
    echo "Creating status.json..."
    echo "{}" > "$STATUS_JSON_PATH"
fi

# Ensure remotes.json exist
REMOTES_JSON_PATH="$CBS_BASEDIR/configs/remotes.json"
if ! [ -f "$REMOTES_JSON_PATH" ]; then
    echo "Creating remotes.json..."
    echo "[]" > "$REMOTES_JSON_PATH"
fi

# Ensure ardupilot git repository for metadata serving exist
AP_REPO_METAGEN_PATH="$CBS_BASEDIR/ardupilot"
if [ ! -d "$AP_REPO_METAGEN_PATH" ] || ! git -C "$AP_REPO_METAGEN_PATH" rev-parse --is-inside-work-tree > /dev/null; then
    rm -rf "$AP_REPO_METAGEN_PATH" 2>/dev/null
    echo "Creating ardupilot repository at $AP_REPO_METAGEN_PATH..."
    git clone https://github.com/ardupilot/ardupilot.git "$AP_REPO_METAGEN_PATH"
fi

if [ "$CBS_ENABLE_INBUILT_BUILDER" -eq 1 ]; then
    # Ensure ardupilot git repository for build generation exist
    AP_REPO_BUILDGEN_PATH="$CBS_BASEDIR/tmp/ardupilot"
    if [ ! -d "$AP_REPO_BUILDGEN_PATH" ] || ! git -C "$AP_REPO_BUILDGEN_PATH" rev-parse --is-inside-work-tree > /dev/null; then
        rm -rf "$AP_REPO_BUILDGEN_PATH" 2>/dev/null
        echo "Creating ardupilot repository at $AP_REPO_BUILDGEN_PATH..."
        git clone https://github.com/ardupilot/ardupilot.git "$AP_REPO_BUILDGEN_PATH"
    fi
fi

# Start app
gunicorn wsgi:application
