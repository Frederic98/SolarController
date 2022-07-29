from flask import Flask, request, Response, render_template
from controller import SolarController
import json
import yaml
import os
import math
from typing import Any

config_file = os.path.join(os.path.dirname(__file__), 'config.yaml')

with open(config_file) as f:
    config = yaml.safe_load(f)


class JSonResponse(Response):
    def __init__(self, response: Any, *args, mimetype='application/json', **kwargs):
        Response.__init__(self, json.dumps(response), *args, mimetype=mimetype, **kwargs)


server = Flask('SolarController')
controller = SolarController(config)


@server.route('/')
def webroot():
    return JSonResponse(controller.data)


@server.route('/temperature', strict_slashes=False)
@server.route('/temperature/<name>', strict_slashes=False)
def temperature(name=None):
    # GET /temperature
    #   => a {name: temperature, ...} dict
    # GET /temperature?detail
    # GET /temperature?detail=true
    #   => a {name: {'value': temperature, 'state': 'CONNECTED', ...}, ...} dict
    detail = request.args.get('detail')
    if detail is not None and detail.lower() in ['', 'true', '1']:
        data = {probe['name']: probe for probe in controller.data['temperature']}
    else:
        data = {probe['name']: probe['value'] for probe in controller.data['temperature']}
    if name is None:
        return JSonResponse(data)
    elif name in data:
        return JSonResponse(data[name])
    else:
        return Response('Not found', 404)


# @server.route('/temperature/<id>')
# def temperature_id(id):
#     return JSonResponse(controller.data['temperature'][id]['value'])


# @server.route('/probes', strict_slashes=False)
# def probes():
#     return JSonResponse(controller.data['temperature'])


@server.route('/relay')
@server.route('/relay/<name>')
def get_relays(name=None):
    data = {relay['name']: relay['state'] for relay in controller.data['relay']}
    if name is not None:
        data = data[name]
    return JSonResponse(data)


@server.route('/pwm')
@server.route('/pwm/<name>', methods=['GET'])
def get_pwm(name=None):
    detail = request.args.get('detail')
    if detail is not None and detail.lower() in ['', 'true', '1']:
        data = {pwm['name']: pwm for pwm in controller.data['pwm']}
    else:
        data = {pwm['name']: pwm['value'] for pwm in controller.data['pwm']}
    if name is None:
        return JSonResponse(data)
    elif name in data:
        return JSonResponse(data[name])
    else:
        return Response('Not found', 404)


@server.route('/analog')
@server.route('/analog/<name>')
def get_analog(name=None):
    detail = request.args.get('detail')
    if detail is not None and detail.lower() in ['', 'true', '1']:
        data = {analog['name']: analog for analog in controller.data['analog']}
    else:
        data = {analog['name']: analog['value'] for analog in controller.data['analog']}
    if name is None:
        return JSonResponse(data)
    elif name in data:
        return JSonResponse(data[name])
    else:
        return Response('Not found', 404)


@server.route('/relay/<name>', methods=['POST'])
def set_relay(name):
    state = request.json
    assert isinstance(state, bool)
    controller.set_relay(name, state)
    return JSonResponse(state)


@server.route('/pwm/<name>', methods=['POST'])
def set_pwm(name):
    value = request.json
    assert isinstance(value, (int, float))
    assert not any([math.isnan(value), math.isinf(value)])
    controller.set_pwm(name, value)
    return JSonResponse(value)


@server.route('/status')
def server_status():
    status = {
        'serial_link': {
            'alive': controller.serial_thread.is_alive(),
            'msg': controller.serial_thread.traceback
        }
    }
    status.update(controller.data['health'])
    return JSonResponse(status)


@server.before_request
def limit_post_to_localhost():
    if config['system']['http']['post_localhost_only'] \
            and request.method.upper() == 'POST' \
            and request.remote_addr != '127.0.0.1':
        return Response('POST requests are only allowed by myself.', status=403, mimetype='text/plain')


@server.route('/debug')
def server_debug():
    return render_template('debug.html', relays=[relay['name'] for relay in controller.data['relay']])


@server.route('/index.html')
def server_index():
    return render_template('index.html')


if __name__ == "__main__":
    server.debug = True
    server.run(config['system']['http']['address'], config['system']['http']['port'], debug=True, use_reloader=False)
