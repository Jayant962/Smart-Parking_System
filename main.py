from flask import Flask,render_template,request

app = Flask(__name__)

@app.route("/")
def start():
    return render_template("login.html")

@app.route("/signup", methods=["GET", "POST"])
def home():
    if request.method == "POST":
        name = request.form.get("name")
        email = request.form.get("email")
        password = request.form.get("password")

        return render_template("booking.html")   # or redirect later

    return render_template("signup.html")

@app.route('/login')
def login():
    return render_template('login.html')

@app.route("/submit",methods=["GET","POST"])
def submit():
    return render_template('booking.html')

if __name__ == '__main__':
    app.run(debug=True)