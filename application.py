
import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True


# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    # Query db for user's current holdings
    portfolio = db.execute("SELECT name, symbol, total_shares AS shares FROM stocks JOIN current ON stocks.id = current.stock_id WHERE user_id = ?", session["user_id"])
    
    # Update each stock in portfolio with current price & total value of each stock holding and calculate total value of all stocks
    total_stock_value = 0
    for row in portfolio:
        price = lookup(row["symbol"])["price"]
        total_value = price * row["shares"]
        row.update({"price": price, "total_value": total_value})
        total_stock_value += total_value
        
     # Query user table for cash balance   
    cash = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])[0]["cash"]
    
    # Create dict with user equity data
    equity = {"cash": cash, "total_stock_value": total_stock_value, "total_equity": total_stock_value + cash}
   
    # Display portfolio * equity data on homepage
    return render_template("index.html", portfolio = portfolio, equity = equity)

@app.route("/add", methods=["GET", "POST"])
@login_required
def add():
    """Add cash"""
    # User reached route via post method
    if request.method == "POST":
        deposit = request.form.get("deposit")
        deposit = int(deposit)
        
        # Error message if blank input
        if not deposit:
            return apology("Please enter an amount to deposit", code=400)
        
        # calculate new balance and update user data
        balance = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])
        new_balance = balance[0]["cash"] + deposit
        db.execute("UPDATE users SET cash = ? WHERE id = ?", new_balance, session["user_id"])
        
    # Return to index.html
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("add.html")
        
@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    # User reached route via post method
    if request.method == "POST":
        #Assign symbol and shares(as integer) to variables
        symbol = request.form.get("symbol")
        shares = int(request.form.get("shares"))

        # Error message if no input in symbol field
        if not symbol:
            return apology("Please enter a valid stock symbol", code=400)

        # Error message if share value less than 1
        if shares < 1:
            return apology("Please enter at least one share", code=400)
            
        if isinstance(shares, int) == False:
            return apology("Please enter at least one share using whole numbers", code=400)

        # Use lookup function to find current price and return error message if symbol is not valid
        quote = lookup(symbol)
        if quote == None:
            return apology("Please enter a valid stock symbol", code=400)

        # Assign stock price and stock price * shares requested to variables
        price = int(quote["price"])
        purchase_price = price * shares

        # Query users table to find cash balance & assign to variable
        balance = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])

        # Error message if user balance is less than total purchase price
        if balance[0]["cash"] < purchase_price:
            return apology("You don't have enough cash for this purchase", code=400)

        # Add stock to stock table if not already there
        if not db.execute("SELECT * FROM stocks WHERE symbol = ?", symbol):
            db.execute("INSERT INTO stocks(symbol, name) VALUES(?, ?)", symbol, quote["name"])

        # Assign stock id from stocks table to variable
        stockid = db.execute("SELECT id FROM stocks WHERE symbol = ?", symbol)

        # Add this buy to history table
        db.execute("INSERT INTO history(user_id, action, stock_id, price, shares) VALUES(?, ?, ?, ?, ?)", session["user_id"], "buy", stockid[0]["id"], price, shares)

        # Update current table to reflect number of stocks owned after purchase
        # If user already owns this stock, add shares to the row
        current_shares = db.execute("SELECT total_shares FROM current WHERE user_id = ? AND stock_id = ?", session["user_id"], stockid[0]["id"])
        if current_shares:
            db.execute("UPDATE current SET total_shares = ?", shares + int(current_shares[0]["total_shares"]))

        #If user does not already own this stock, create new row
        else:
            db.execute("INSERT INTO current(user_id, stock_id, total_shares) VALUES(?, ?, ?)", session["user_id"], stockid[0]["id"], shares)

        # Update user cash balance
        new_balance = balance[0]["cash"] - purchase_price
        db.execute("UPDATE users SET cash = ? WHERE id = ?", new_balance, session["user_id"])

        # Return to index.html
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("buy.html")

@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    history = db.execute("SELECT datetime, action, symbol, price, shares FROM history JOIN stocks ON stocks.id = history.stock_id WHERE user_id = ?", session["user_id"])
    
    return render_template("history.html", history = history)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        symbol = request.form.get("symbol")
        # Error message if no input in symbol field
        if not symbol:
            return apology("Please enter a valid stock symbol", code=400)

        # Use lookup function to find current price and return error message if symbol is not valid
        quote = lookup(symbol)
        if quote == None:
            return apology("Please enter a valid stock symbol", code=400)
            
        # Display quote
        return render_template("quoted.html", quote=quote)

   # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("quote.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Assign username input to variable and return error message if empty
        username = request.form.get("username")
        if not username:
            return apology("Please enter a username", code=400)

        # Query database to see if user name exists
        user_check = db.execute('SELECT username FROM users WHERE username = ?', username)

        #Error message if user name exists
        if user_check:
            return apology("Username already exists", code=400)

        # Return error message if empty password field
        password = request.form.get("password")
        if not password:
            return apology("Please enter a password", code=400)

        # Ensure both passwords match
        confirmation = request.form.get("confirmation")
        if password != confirmation:
            return apology("Passwords do not match", code=400)

        # Hash password and store in user info in users table
        hashed_password =  generate_password_hash(password)
        db.execute("INSERT INTO users(username, hash) VALUES(?, ?)", username, hashed_password)

        # Return to log in page
        return render_template("login.html")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    # User reached route via post method
    if request.method == "POST":

        #Assign symbol and shares(as integer) to variables
        symbol = request.form.get("symbol")
        shares = request.form.get("shares")
        shares = int(shares)

        # Error message if no input in symbol field
        if not symbol:
            return apology("Please enter a valid stock symbol", code=400)

        # Error message if share value less than 1
        if shares < 1:
            return apology("Please enter at least one share", code=400)

        # Query current table to confirm user owns enough shares to sell and return error message if not
        currently_held = db.execute("SELECT total_shares FROM current WHERE user_id = ? AND stock_id IN (SELECT id FROM stocks WHERE symbol = ?)", session["user_id"], symbol)
        if not currently_held or int(currently_held[0]["total_shares"]) < shares:
            return apology("You do not have enough shares of this stock to complete transaction", code=400)

        # Assign stock price and stock price * shares requested to variables
        price = lookup(symbol)["price"]
        sale_price = price * shares

        # Assign stock id from stocks table to variable
        stockid = db.execute("SELECT id FROM stocks WHERE symbol = ?", symbol)

        # Add this sale to history table
        db.execute("INSERT INTO history(user_id, action, stock_id, price, shares) VALUES(?, ?, ?, ?, ?)", session["user_id"], "sale", stockid[0]["id"], price, shares)

        # Update current table to reflect number of stocks owned after purchase
        # Query current table to find shares currently held
        current_shares = db.execute("SELECT total_shares FROM current WHERE user_id = ? AND stock_id = ?", session["user_id"], stockid[0]["id"])

        # Calculate update shares
        updated_shares = int(current_shares[0]["total_shares"]) - shares

        # If user still holds shares, update table
        if updated_shares > 0:
            db.execute("UPDATE current SET total_shares = ? WHERE user_id = ? and stock_id = ?", updated_shares, session["user_id"], stockid[0]["id"])

        # If all shares are sold, delete row
        else:
            db.execute("DELETE FROM current WHERE user_id = ? and stock_id = ?", session["user_id"], stockid[0]["id"])

        # Update user cash balance
        balance = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])
        new_balance = balance[0]["cash"] + sale_price
        db.execute("UPDATE users SET cash = ? WHERE id = ?", new_balance, session["user_id"])

        # Return to index.html
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        # Query db for currently held stocks and use to create select menu options in sell page form
        current_stocks = db.execute("SELECT symbol FROM stocks WHERE id IN (SELECT stock_id FROM current WHERE user_id = ?)", session["user_id"])
        return render_template("sell.html", current_stocks = current_stocks)



def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
