import os
import json
import config
from app.db import Database
from app.keys import KeyRing
from app.geo import search_places
from app.image import save_image
from flask_caching import Cache
from flask_sse import sse
from datetime import datetime, timezone, timedelta
from flask import Blueprint, abort, request, render_template, jsonify, send_from_directory

bp = Blueprint('main', __name__)
kr = KeyRing(config.KEYS_FILE)
db = Database(config.DB_PATH)
cache = Cache(config=config.CACHE)


def get_conf(loc):
    try:
        return config.LOCATIONS[loc]
    except KeyError:
        abort(404)


@bp.route('/')
def index():
    # List all live locations
    return render_template('index.html',
            locations=[k for k in config.LOCATIONS.keys()
                if config.LOCATIONS[k]['LIVE']])


@bp.route('/version')
@cache.cached(timeout=600)
def version():
    return jsonify(version=config.VERSION)


@bp.route('/<location>/')
def map(location):
    conf = get_conf(location)
    return render_template('map.html', conf=conf, location=location)


@bp.route('/<location>/log/<type>', methods=['GET', 'POST'])
@cache.cached(timeout=5,
              unless=lambda: request.method != 'GET',
              make_cache_key=lambda *args, **kwargs: '{}_{}'.format(
                  request.path,
                  request.headers.get('X-AUTH', 'noauth')))
def log(location, type):
    conf = get_conf(location)
    key = request.headers.get('X-AUTH')
    auth = kr.check_key(key, location)

    if request.method == 'POST':
        if not auth: abort(401)

        # Grab submitted log data
        data = request.form.to_dict()

        # If an image was submitted, save it
        if request.files.get('image'):
            filename = save_image(request.files['image'])
            if filename is None:
                abort(400)
            data['image'] = filename

        # Add the log data
        db.add(type, location, key, data)

        # Clear cache so new requests get latest data
        cache.clear()

        # Ping clients to grab latest data
        timestamp = datetime.utcnow().replace(tzinfo=timezone.utc).timestamp()
        sse.publish(json.dumps(
            {'data': data, 'timestamp': timestamp}), channel=location)
        return jsonify(success=True)
    else:
        if type == 'event':
            # Limit amount of event logs that are sent
            now = datetime.utcnow().replace(tzinfo=timezone.utc)
            interval = (now - timedelta(**config.LOGS_AFTER)).timestamp()
            logs = db.logs(location, n=config.MAX_LOGS, after=interval, type='event')
        elif type == 'pinned':
            # For pinned, only return latest
            logs = db.logs(location, n=1, type='pinned')
        else:
            logs = db.logs(location, type=type)

        # Strip submitter info
        # Check permissions
        for l in logs:
            submitter = l.pop('submitter')
            if auth and (auth == 'prime' or key.startswith(submitter)):
                l['permit'] = True
        return jsonify(logs=logs)


@bp.route('/<location>/log/<type>/all')
@cache.cached(timeout=5)
def all_logs(location, type):
    conf = get_conf(location)
    logs = db.logs(location, type=type)

    # Strip submitter info
    # Check permissions
    for l in logs:
        l.pop('submitter')
    return jsonify(logs=logs)


@bp.route('/<location>/log/edit', methods=['POST'])
def edit_log(location):
    key = request.headers.get('X-AUTH')
    auth = kr.check_key(key, location)

    # Abort if not authed at all
    if not auth:
        abort(401)

    if request.method == 'POST':
        data = request.get_json()
        action = data['action']
        timestamp = data['timestamp']

        # See if a log matches the request
        log = db.log(location, timestamp)
        if log is None: abort(404)

        # Abort if not prime key or not submitter
        if auth == 'prime' or key == log['submitter']:
            if action == 'delete':
                db.delete(location, timestamp)
                cache.clear()
                sse.publish('delete' , channel=location)
                return jsonify(success=True)

            elif action == 'update':
                for k, v in data['changes'].items():
                    log['data'][k] = v
                db.update(location, timestamp, log['data'])
                cache.clear()
                sse.publish('update' , channel=location)
                return jsonify(success=True)
            return jsonify(success=False, error='Unknown action')
        else:
            abort(401)
    return jsonify(success=False)

# Get a list of possible lat/lngs for a location query
@bp.route('/<location>/location', methods=['POST'])
def query_location(location):
    conf = get_conf(location)
    key = request.headers.get('X-AUTH')
    if not kr.check_key(key, location):
        abort(401)
    data = request.get_json()
    results = search_places(data['query'], conf)
    return jsonify(results=results)

@bp.route('/img/<fname>')
def image(fname):
    return send_from_directory(os.path.join('..', config.UPLOAD_PATH), fname)


# Panel (key management backend)
@bp.route('/<location>/panel')
def panel(location):
    conf = get_conf(location)
    return render_template('panel.html', conf=conf)

@bp.route('/<location>/keys', methods=['GET', 'POST'])
def keys(location):
    key = request.headers.get('X-AUTH')
    if not kr.check_key(key, location) == 'prime':
        abort(401)

    if request.method == 'POST':
        data = request.get_json()
        action = data['action']
        if action == 'revoke':
            kr.del_key(location, 'write', data['key'])
            return jsonify(success=True)
        elif action == 'create':
            key = kr.new_key()
            kr.add_key(location, 'write', key)
            return jsonify(success=True, key=key)
        return jsonify(success=False)

    keys = kr.get_keys(location).get('write')
    return jsonify(keys=keys)

@bp.route('/<location>/checkauth', methods=['POST'])
def check_auth(location):
    key = request.headers.get('X-AUTH')
    typ = kr.check_key(key, location)
    return jsonify(success=bool(typ))
