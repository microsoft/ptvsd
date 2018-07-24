from flask import Flask
from flask import render_template


app = Flask(__name__)


@app.route("/")
def home():
    return render_template(
        "hello.html",
        title='Hello',
        content='Flask-Jinja-Test'
    )


@app.route("/exit")
def exitapp():
    from flask import request
    func = request.environ.get('werkzeug.server.shutdown')
    if func is None:
        raise RuntimeError('No shutdown')
    func()
    return 'Done'
