#!/usr/bin/env python3

import os
import base64
from flask import Flask, render_template, request, send_from_directory, jsonify
from threading import Thread
import sys
import requests

from logging.config import dictConfig

dictConfig({
    'version': 1,
    'formatters': {'default': {
        'format': '[%(asctime)s] %(levelname)s in %(module)s: %(message)s',
    }},
    'handlers': {'wsgi': {
        'class': 'logging.StreamHandler',
        'stream': 'ext://flask.logging.wsgi_errors_stream',
        'formatter': 'default'
    }},
    'root': {
        'level': os.getenv('CBS_LOG_LEVEL', default='INFO'),
        'handlers': ['wsgi']
    }
})

# let app.py know about the modules in the parent directory
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import ap_git
import metadata_manager
import build_manager
from builder import Builder

# run at lower priority
os.nice(20)

import optparse
parser = optparse.OptionParser("app.py")

parser.add_option("", "--basedir", type="string",
                  default=os.getenv(
                      key="CBS_BASEDIR",
                      default=os.path.abspath(os.path.join(os.path.dirname(__file__),"..","base"))
                  ),
                  help="base directory")

cmd_opts, cmd_args = parser.parse_args()

# define directories
basedir = os.path.abspath(cmd_opts.basedir)
sourcedir = os.path.join(basedir, 'ardupilot')
outdir_parent = os.path.join(basedir, 'artifacts')
workdir_parent = os.path.join(basedir, 'workdir')

appdir = os.path.dirname(__file__)

builds_dict = {}
REMOTES = None

repo = ap_git.GitRepo.clone_if_needed(
    source="https://github.com/ardupilot/ardupilot.git",
    dest=sourcedir,
    recurse_submodules=True,
)

ap_src_metadata_fetcher = metadata_manager.APSourceMetadataFetcher(
    ap_repo=repo,
    caching_enabled=True,
    redis_host=os.getenv('CBS_REDIS_HOST', default='localhost'),
    redis_port=os.getenv('CBS_REDIS_PORT', default='6379'),
)
versions_fetcher = metadata_manager.VersionsFetcher(
    remotes_json_path=os.path.join(basedir, 'configs', 'remotes.json'),
    ap_repo=repo
)

manager = build_manager.BuildManager(
    outdir=outdir_parent,
    redis_host=os.getenv('CBS_REDIS_HOST', default='localhost'),
    redis_port=os.getenv('CBS_REDIS_PORT', default='6379')
)
cleaner = build_manager.BuildArtifactsCleaner()
progress_updater = build_manager.BuildProgressUpdater()
vehicles_manager = metadata_manager.VehiclesManager.get_singleton()

versions_fetcher.start()
cleaner.start()
progress_updater.start()

if os.getenv('CBS_ENABLE_INBUILT_BUILDER', default='1') == '1':
    builder = Builder(
        workdir=workdir_parent,
        source_repo=repo
    )
    builder_thread = Thread(
        target=builder.run,
        daemon=True
    )
    builder_thread.start()

app = Flask(__name__, template_folder='templates')

versions_fetcher.reload_remotes_json()
app.logger.info('Python version is: %s' % sys.version)


def parse_version_id(version_id):
    """
    Parse composite version_id into remote_name and commit_ref.
    Format: {remote_name}:{base64_encoded_commit_ref}
    Returns: (remote_name, commit_ref) or (None, None) if invalid
    """
    try:
        remote_name, encoded_commit_ref = version_id.split(':', 1)
        commit_ref = base64.urlsafe_b64decode(encoded_commit_ref).decode()
        return remote_name, commit_ref
    except Exception:
        return None, None


def create_version_id(remote_name, commit_ref):
    """
    Create composite version_id from remote_name and commit_ref.
    Format: {remote_name}:{base64_encoded_commit_ref}
    """
    encoded_commit_ref = base64.urlsafe_b64encode(commit_ref.encode()).decode()
    return f"{remote_name}:{encoded_commit_ref}"


def get_auth_token():
    try:
        # try to read the secret token from the file
        with open(os.path.join(basedir, 'secrets', 'reload_token'), 'r') as file:
            token = file.read().strip()
            return token
    except (FileNotFoundError, PermissionError):
        app.logger.error("Couldn't open token file. Checking environment for token.")
        # if the file does not exist, check the environment variable
        return os.getenv('CBS_REMOTES_RELOAD_TOKEN')

@app.route('/api/v1/admin/refresh_remotes', methods=['POST'])
def refresh_remotes():
    auth_token = get_auth_token()

    if auth_token is None:
        app.logger.error("Couldn't retrieve authorization token")
        return jsonify({'error': 'Internal Server Error'}), 500

    data = request.get_json()
    token = data.get('token') if data else None
    if not token or token != auth_token:
        return jsonify({'error': 'Unauthorized'}), 401

    versions_fetcher.reload_remotes_json()
    return jsonify({'message': 'Successfully refreshed remotes'}), 200

@app.route('/api/v1/builds', methods=['POST'])
def create_build():
    """Create a new build"""
    try:
        data = request.get_json()

        if not data:
            return jsonify({'error': 'Request body must be JSON'}), 400

        version_id = data.get('version_id')
        if not version_id:
            return jsonify({'error': 'version_id is required'}), 400

        # Parse composite version_id
        remote_name, commit_ref = parse_version_id(version_id)
        if not remote_name or not commit_ref:
            return jsonify({'error': 'Invalid version_id format'}), 400

        remote_info = versions_fetcher.get_remote_info(remote_name)
        if remote_info is None:
            return jsonify({
                'error': f'Remote {remote_name} is not whitelisted'
            }), 400

        vehicle = data.get('vehicle')
        if not vehicle:
            return jsonify({'error': 'vehicle is required'}), 400

        version_info = versions_fetcher.get_version_info(
            vehicle_name=vehicle,
            remote=remote_name,
            commit_ref=commit_ref
        )

        if version_info is None:
            return jsonify({'error': 'Invalid version for vehicle'}), 400

        board = data.get('board')
        if not board:
            return jsonify({'error': 'board is required'}), 400

        with repo.get_checkout_lock():
            boards_at_commit = ap_src_metadata_fetcher.get_boards(
                remote=remote_name,
                commit_ref=commit_ref,
                vehicle=vehicle,
            )

        if board not in boards_at_commit:
            return jsonify({'error': 'Invalid board for this version'}), 400

        selected_features = set(data.get('selected_features', []))

        git_hash = repo.commit_id_for_remote_ref(
            remote=remote_name,
            commit_ref=commit_ref
        )

        build_info = build_manager.BuildInfo(
            vehicle=vehicle,
            remote_info=remote_info,
            git_hash=git_hash,
            board=board,
            selected_features=selected_features
        )

        forwarded_for = request.headers.get('X-Forwarded-For', None)
        if forwarded_for:
            client_ip = forwarded_for.split(',')[0].strip()
        else:
            client_ip = request.remote_addr

        build_id = manager.submit_build(
            build_info=build_info,
            client_ip=client_ip,
        )

        app.logger.info(f'Build {build_id} submitted successfully')

        return jsonify({
            'build_id': build_id,
            'url': f'/api/v1/builds/{build_id}',
            'status': 'submitted'
        }), 201
    except Exception as ex:
        app.logger.error(f'Error creating build: {ex}')
        return jsonify({'error': str(ex)}), 400

@app.route('/add_build')
def add_build():
    app.logger.info('Rendering add_build.html')
    return render_template('add_build.html')


def filter_build_options_by_category(build_options, category):
    return sorted([f for f in build_options if f.category == category], key=lambda x: x.description.lower())

def parse_build_categories(build_options):
    return sorted(list(set([f.category for f in build_options])))

@app.route('/', defaults={'token': None}, methods=['GET'])
@app.route('/viewlog/<token>', methods=['GET'])
def home(token):
    if token:
        app.logger.info("Showing log for build id " + token)
    app.logger.info('Rendering index.html')
    return render_template('index.html', token=token)

@app.route("/builds/<string:build_id>/artifacts/<path:name>", methods=['GET'])
def download_file(build_id, name):
    path = os.path.join(
        basedir,
        'artifacts',
        build_id,
    )
    app.logger.info('Downloading %s/%s' % (path, name))
    return send_from_directory(path, name, as_attachment=False)

@app.route("/api/v1/vehicles/<string:vehicle_name>/versions/<path:version_id>/boards", methods=['GET'])
def get_boards(vehicle_name, version_id):
    """Get available boards for a specific vehicle and version"""
    # Parse composite version_id
    remote_name, commit_reference = parse_version_id(version_id)
    if not remote_name or not commit_reference:
        return jsonify({'error': 'Invalid version_id format'}), 400

    is_version_listed = versions_fetcher.is_version_listed(
        vehicle_name=vehicle_name,
        remote=remote_name,
        commit_ref=commit_reference
    )
    if not is_version_listed:
        return jsonify({
            'error': 'Commit reference not allowed to build for the vehicle'
        }), 400

    app.logger.info(
        'Board list requested for %s %s %s' % (
            vehicle_name, remote_name, commit_reference
        )
    )

    # getting board list for the branch
    boards = ap_src_metadata_fetcher.get_boards(
        remote=remote_name,
        commit_ref=commit_reference,
        vehicle=vehicle_name,
    )

    if not boards:
        return jsonify({
            'error': 'No boards found for this vehicle and version'
        }), 404

    return jsonify({
        'vehicle': vehicle_name,
        'version_id': version_id,
        'boards': boards,
        'default_board': boards[0]
    })

@app.route("/api/v1/vehicles/<string:vehicle_name>/versions/<path:version_id>/features", methods=['GET'])
def get_features(vehicle_name, version_id):
    """Get available build features/options for a vehicle and version"""
    # Parse composite version_id
    remote_name, commit_reference = parse_version_id(version_id)
    if not remote_name or not commit_reference:
        return jsonify({'error': 'Invalid version_id format'}), 400

    is_version_listed = versions_fetcher.is_version_listed(
        vehicle_name=vehicle_name,
        remote=remote_name,
        commit_ref=commit_reference
    )
    if not is_version_listed:
        return jsonify({
            'error': 'Commit reference not allowed to build for the vehicle'
        }), 400

    app.logger.info(
        'Build options requested for %s %s %s' % (
            vehicle_name, remote_name, commit_reference
        )
    )

    # getting build options for the commit
    options = ap_src_metadata_fetcher.get_build_options_at_commit(
        remote=remote_name,
        commit_ref=commit_reference
    )

    # parse the set of categories from these objects
    categories = parse_build_categories(options)
    features = []
    for category in categories:
        filtered_opts = filter_build_options_by_category(options, category)
        category_options = []
        for option in filtered_opts:
            category_options.append({
                'label': option.label,
                'description': option.description,
                'default': option.default,
                'define': option.define,
                'dependency': option.dependency,
            })
        features.append({
            'name': category,
            'options': category_options,
        })

    return jsonify({
        'vehicle': vehicle_name,
        'version_id': version_id,
        'features': features
    })

@app.route("/api/v1/vehicles/<string:vehicle_name>/versions", methods=['GET'])
def get_versions(vehicle_name):
    versions = list()
    for version_info in versions_fetcher.get_versions_for_vehicle(vehicle_name=vehicle_name):
        if version_info.release_type == "latest":
            title = f"Latest ({version_info.remote})"
        else:
            title = f"{version_info.release_type} {version_info.version_number} ({version_info.remote})"
        version_id = create_version_id(version_info.remote, version_info.commit_ref)
        versions.append({
            "title": title,
            "id": version_id,
            "remote": version_info.remote,
            "commit_ref": version_info.commit_ref,
            "release_type": version_info.release_type,
            "version_number": version_info.version_number,
        })

    return jsonify({
        'vehicle': vehicle_name,
        'versions': sorted(versions, key=lambda x: x['title'])
    })

@app.route("/api/v1/vehicles", methods=['GET'])
def get_vehicles():
    vehicles = vehicles_manager.get_all_vehicle_names_sorted()
    return jsonify({
        'vehicles': [{'name': v} for v in vehicles]
    })

@app.route("/api/v1/vehicles/<string:vehicle_name>/versions/<path:version_id>/boards/<string:board_name>/defaults", methods=['GET'])
def get_deafults(vehicle_name, version_id, board_name):
    # Parse composite version_id
    remote_name, commit_reference = parse_version_id(version_id)
    if not remote_name or not commit_reference:
        return jsonify({'error': 'Invalid version_id format'}), 400

    # Heli is built on copter
    if vehicle_name == "Heli":
        vehicle_name = "Copter"
        board_name += "-heli"

    version_info = versions_fetcher.get_version_info(vehicle_name=vehicle_name, remote=remote_name, commit_ref=commit_reference)

    if version_info is None:
        return jsonify({
            'error': f'Commit reference not allowed for builds for {vehicle_name} on {remote_name} remote'
        }), 400

    artifacts_dir = version_info.ap_build_artifacts_url

    if artifacts_dir is None:
        return jsonify({
            'error': 'Could not find artifacts for requested release/branch/commit on ardupilot server'
        }), 404

    url_to_features_txt = artifacts_dir + '/' + board_name + '/features.txt'
    response = requests.get(url_to_features_txt, timeout=30)

    if not response.status_code == 200:
        return jsonify({
            'error': 'Could not retrieve features.txt for given vehicle, version and board combination',
            'status_code': response.status_code,
            'url': url_to_features_txt
        }), response.status_code
    # split response by new line character to get a list of defines
    result = response.text.split('\n')
    # omit the last two elements as they are always blank
    return jsonify(result[:-2])

@app.route('/api/v1/builds', methods=['GET'])
def get_all_builds():
    all_build_ids = manager.get_all_build_ids()
    all_build_info = [
        {
            **manager.get_build_info(build_id).to_dict(),
            'build_id': build_id
        }
        for build_id in all_build_ids
    ]

    all_build_info_sorted = sorted(
        all_build_info,
        key=lambda x: x['time_created'],
        reverse=True,
    )

    return jsonify({
        'builds': all_build_info_sorted,
        'count': len(all_build_info_sorted)
    }), 200

@app.route('/api/v1/builds/<string:build_id>', methods=['GET'])
def get_build_by_id(build_id):
    if not manager.build_exists(build_id):
        return jsonify({
            'error': f'build with id {build_id} does not exist.'
        }), 404

    response = {
        **manager.get_build_info(build_id).to_dict(),
        'build_id': build_id
    }

    return jsonify(response), 200

if __name__ == '__main__':
    app.run()
