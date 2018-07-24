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
