import os
import random
import MySQLdb
import datetime
import time
import json
# Import the Flask Framework
from flask import Flask, jsonify, request, abort, render_template, flash, redirect
app = Flask(__name__)
app.config.from_object('config')

# Note: We don't need to call run() since our application is embedded within
# the App Engine WSGI application server.

def getDB():
	if os.getenv('SERVER_SOFTWARE', '').startswith('Google App Engine/'):
		db = MySQLdb.connect(
			unix_socket='/cloudsql/{}'.format(
				os.environ['CLOUDSQL_INSTANCE']),
				user=os.environ['CLOUDSQL_USERNAME'],
				passwd=os.environ['CLOUDSQL_PASSWORD'],
				db=os.environ['CLOUDSQL_DATABASE'])
	else:
		#REMOVE FOR DEPLOYMENT
		db = MySQLdb.connect("104.154.38.165", "root", os.environ['CLOUDSQL_PASSWORD'], "casso1")
	return db

db = getDB()
cursor = db.cursor()

#Website handling functions
#Start here

@app.route('/')
def hello():
	"""Return a friendly HTTP greeting."""
	return "Hello again!"

@app.route('/api/v1.0/registerWebsite', methods=['POST'])
def webRegisterWebsite():
	#Arguments are website url
	#Must be done manually currently
	if not request.json or not 'emailaddress' in request.get_json(force=True, silent=True):
		abort(400, 'ohno')
	return jsonify({'status' : 'success'})

@app.route('/api/v1.0/registerUser', methods=['POST'])
def webRegisterUser():
	#Arguments are optional username, email address, api key, phone number, ip address, phone-id
	if not request.get_json(force=True, silent=True):
		abort(400, "Request in the wrong format")
	req = request.get_json(force=True)
	if not 'emailaddress' in req:
		abort(400, "Email address missing")
	if not 'apikey' in req:
		abort(400, "Api key missing")
	if not 'phonenumber' in req:
		abort(400, "Phone number missing")
	if not 'phone-id' in req:
		abort(400, "Phone ID missing")

	#Get the website's id or reject if incorrect
	websiteID = getWebsiteID(req['apikey'])
	if websiteID is None:
		abort(400, "Incorrect API Key")

    #Verify that the emailaddress does not exist again on that website
	if checkUserExists(req['emailaddress'], req['phonenumber'], websiteID) is True:
		abort(400, "User already with that email or phone number already exists")

	#Create a new user entry
	try:
		if 'username' in req:
			sql = "INSERT INTO users (username, emailaddress, phonenumber, website_id) VALUES (%s,%s,%s,%s)"
			cursor.execute(sql, (req['username'], req['emailaddress'], req['phonenumber'], websiteID))
			db.commit()
		else:
			sql = "INSERT INTO users (emailaddress, phonenumber, website_id) VALUES (%s,%s,%s)"
			cursor.execute(sql, (req['emailaddress'], req['phonenumber'], websiteID))
			db.commit()

		sql = "UPDATE users SET phone_id=%s WHERE emailaddress=%s"
		cursor.execute(sql, (req['phone-id'], req['emailaddress']))
	except:
		abort(400, "database error during user creation")

	return jsonify({'status' : 'success'})

def getWebsiteID(apikey):
	try:
		cursor.execute('SELECT pid from websites WHERE secretkey=%s', (apikey,))
		if cursor.rowcount > 0:
			result = cursor.fetchone()
			return int(result[0])
		else:
			return None
	except:
		print("get website id error")
		abort(400, "get website id error")

def checkUserExists(emailaddress, phonenumber, websiteid):
	try:
		sql1 = "SELECT pid from users WHERE emailaddress=%s AND website_id=%s"
		cursor.execute(sql1, (emailaddress, websiteid))
		if cursor.rowcount > 0:
			return True
		else:
			sql2 = "SELECT pid from users WHERE website_id=%s AND phonenumber=%s"
			cursor.execute(sql2, (websiteid, phonenumber))
			if cursor.rowcount  > 0:
				return True
			else:
				return False
	except:
		print("check user error")
		abort(400, "check user error")

def randKey(digits):
	return ''.join(random.choice(
		'0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz') for i in range(digits))

@app.route('/api/v1.0/authenticateUser', methods=['POST'])
def webAuthenticateUser():
	#Arguments are optional either username or email, apikey, ipaddress of request to authenticate
	if not request.get_json(force=True, silent=True):
		abort(400, "Request in the wrong format")
	req = request.get_json(force=True)
	if 'apikey' not in req:
		abort(400, "Api key missing")
	if 'ipaddress' not in req:
		abort(400, "IP address of client missing")

	#Check the website's secret key
	websiteID = getWebsiteID(req['apikey'])
	if websiteID is None:
		abort(400, "Incorrect API Key")

	#Verify username/email and mark user down for authentication (update timestamp)
	user_id = 0
	if 'emailaddress' in req:
		sql = "SELECT pid from users WHERE emailaddress=%s AND website_id=%s"
		cursor.execute(sql, (req['emailaddress'], websiteID))
		if cursor.rowcount > 0:
			user_id = int(cursor.fetchone()[0])
		else:
			abort(400, "Incorrect Email address (does not exist in database)")
	elif 'username' in req:
		sql = "SELECT pid from users WHERE username=%s AND website_id=%s"
		cursor.execute(sql, (req['username'], websiteID))
		if cursor.rowcount > 0:
			user_id = int(cursor.fetchone()[0])
		else:
			abort(400, "Incorrect Username (does not exist in database)")
	else:
		abort(400, "No username or email address provided to authenticate")

	#Save record of authentication
	saveInteraction(req['ipaddress'], user_id)

	try:
		sql = "UPDATE users SET last_auth_request=NOW() WHERE pid=%s"
		cursor.execute(sql, (user_id,))
		db.commit()
	except:
		abort(400, "Failed to update user account")

	return jsonify({'status':'success'})

def saveInteraction(ipaddress, user_id):
	try:
		sql = "INSERT INTO comms (ipaddress, user_id) VALUES (%s, %s)"
		cursor.execute(sql, (ipaddress, user_id))
		db.commit()
	except:
		abort(400, "Failed to add interaction to database")

@app.route('/api/v1.0/removeUser', methods=['POST'])
def webRemoveUser():
	#Arguments are email address, api key, and phone number (all required)
	if not request.get_json(force=True, silent=True):
		abort(400, "Request in the wrong format")
	req = request.get_json(force=True)
	if not 'emailaddress' in req:
		abort(400, "Email address missing")
	if not 'apikey' in req:
		abort(400, "Api key missing")
	if not 'phonenumber' in req:
		abort(400, "Phone number missing")

	#Get the website's id or reject if incorrect
	websiteID = getWebsiteID(req['apikey'])
	if websiteID is None:
		abort(400, "Incorrect API Key")

	#Check to make sure user exists
	#Unshielded code: Prone to erroring
	sql = "SELECT pid from users WHERE website_id=%s AND phonenumber=%s AND emailaddress=%s"
	cursor.execute(sql, (websiteID, req['phonenumber'], req['emailaddress']))
	if cursor.rowcount < 1:
		abort(400, "User that you are trying to delete does not exist")
	user_id = int(cursor.fetchone()[0])

	#TODO: Verify that the server has not deleted too many accounts recently
	#Remove user from the database
	try:
		sql = "DELETE from users where pid=%s"
		cursor.execute(sql, (user_id,))
		db.commit()
	except:
		print("user deletion failed")
		abort(400, "Failed to access database to delete user")

	return jsonify({'status':'success'})

@app.route('/api/v1.0/checkIfDeviceAuthed/<int:user_id>', methods=['GET'])
def checkIfDeviceAuthed(user_id):
	sql = "SELECT last_device_auth from users WHERE pid=%s"
	cursor.execute(sql, (user_id,))
	if cursor.rowcount > 0:
		#Success
		last_device_auth = cursor.fetchone()[0]


#Functions for mobile support
#Start here

def getUserFromPhone(emailaddress, phonenumber):
	sql = "SELECT pid from users WHERE emailaddress=%s AND phonenumber=%s"
	cursor.execute(sql, (emailaddress, phonenumber))
	if cursor.rowcount > 0:
		#Success
		return int(cursor.fetchone()[0])
	else:
		abort(400, "Incorrect secret phone number or email address")

@app.route('/app/v1.0/registerDevice', methods=['POST'])
def registerDevice():
	#Arguments are phone-id, email, phone number, security questions (4)
	if not request.get_json(force=True, silent=True):
		abort(400, "Request in the wrong format")
	req = request.get_json(force=True)
	if not 'phone-id' in req:
		abort(400, "Phone ID missing")
	if not 'emailaddress' in req:
		abort(400, "Email Address missing")
	if not 'phonenumber' in req:
		abort(400, "Phone number missing")
	if not 'secq1' in req or not 'seca1' in req or not 'secq2' in req or not 'seca2' in req or not 'secq3' in req or not 'seca3' in req or not 'secq4' in req or not 'seca4' in req:
		abort(400, "Security questions incomplete or missing")

	#Get the user in question from the secret phone key
	user_id = getUserFromPhone(req['emailaddress'], req['phonenumber'])
	secretkey = randKey(40)

	#Add security questons and phone-id to user profile
	sql = "INSERT INTO devices (secq1, secq2, secq3, secq4, seca1, seca2, seca3, seca4, phone_id, secretphonekey, user_id) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
	cursor.execute(sql, (req['secq1'], req['secq2'], req['secq3'], req['secq4'], req['seca1'], req['seca2'], req['seca3'], req['seca4'], req['phone-id'],
		secretkey, user_id))
	db.commit()

	return jsonify({"status":"success", "user_id":user_id, "secretphonekey":secretkey})

#Potential security flaw: consider switching to POST request
@app.route('/app/v1.0/checkAuth/<int:user_id>', methods=['GET'])
def checkIfAuthRequired(user_id):
	sql = "SELECT last_auth_request from users WHERE pid=%s"
	cursor.execute(sql, (user_id,))
	if cursor.rowcount > 0:
		#Success
		#Threshold for waiting for authentication: 20 seconds
		#last_auth_time = datetime.datetime.strptime(cursor.fetchone()[0], f)
		last_auth_time = cursor.fetchone()[0]
		if (datetime.datetime.utcnow() - last_auth_time).total_seconds() < 15.0:
			#Authenticated recently, require phone verification
			#return True (1)
			return jsonify({"0": "1"})
		else:
			return jsonify({"0": "0"})
	else:
		abort(400, "User ID does not exist")
		return jsonify({"1":"0"})

#Requires testing
@app.route('/app/v1.0/authenticate', methods=['POST'])
def authenticateByPhone():
	#Arguments are phone number, secret phone key, user id, phone-id
	#Return IP Adress, other client device information
	if not request.get_json(force=True, silent=True):
		abort(400, "Request in the wrong format")
	req = request.get_json(force=True)
	if not 'phonenumber' in req:
		abort(400, "Phone number missing")
	if not 'secretphonekey' in req:
		abort(400, "Secret phone key missing")
	if not 'user_id' in req:
		abort(400, "User ID missing")
	if not 'phone-id' in req:
		abort(400, "Phone ID missing")

	sql = "SELECT user_id from devices WHERE phone_id=%s AND secretphonekey=%s"
	cursor.execute(sql, (req['phone-id'], req['secretphonekey']))
	if cursor.rowcount > 0:
		#Success
		new_user_id = int(cursor.fetchone()[0])
		sql = "SELECT pid from users WHERE phonenumber=%s"
		cursor.execute(sql, (req['phonenumber']))
		if cursor.rowcount > 0:
			#Phone number verified
			if int(cursor.fetchone()[0]) == new_user_id:		
				if new_user_id == req['user_id']:
					#Success, authenticated, set last device authenticated
					sql = "UPDATE users SET last_device_auth=NOW() WHERE user_id=%s AND phonenumber=%s"
					cursor.execute(sql, (new_user_id, req['phonenumber']))
					db.commit()
					sql = "SELECT ipaddress, pid from comms WHERE user_id=%s AND creation_time=(SELECT max(creation_time) from comms WHERE user_id=%s)"
					cursor.execute(sql, (new_user_id, new_user_id))
					if cursor.rowcount > 0:
						#Success
						return jsonify({"status":"success", "ipaddress":cursor.fetchone()[0], "comm_id":cursor.fetchone()[1]})
					else:
						abort(400, "No valid communication found from client")
				else:
					abort(400, "Not allowed for authentication")
			else:
				abort(400, "Phone number does not match other data")
		else:
			abort(400, "Incorrect phone number provided")
	else:
		abort(400, "Incorrect device information provided")

@app.route('/app/v1.0/deactivate', methods=['POST'])
def deactivatePhone():
	#Arguments are secret phone key, user id, phone-id
	#Return status
	if not request.get_json(force=True, silent=True):
		abort(400, "Request in the wrong format")
	req = request.get_json(force=True)
	if not 'secretphonekey' in req:
		abort(400, "Secret phone key missing")
	if not 'user_id' in req:
		abort(400, "User ID missing")
	if not 'phone-id' in req:
		abort(400, "Phone ID missing")

	#Delete phone record from database
	sql = "DELETE FROM devices WHERE secretphonekey=%s, user_id=%s, phone_id=%s"
	cursor.execute(sql, (req['secretphonekey'], req['user_id'], req['phone-id']))
	db.commit()

#Error handling functions
#Start here

@app.errorhandler(404)
def page_not_found(e):
    """Return a custom 404 error."""
    return 'Sorry, Nothing at this URL.', 404


@app.errorhandler(500)
def application_error(e):
    """Return a custom 500 error."""
    return 'Sorry, unexpected error: {}'.format(e), 500


#Website begins here:

#Requires testing
#Requires error handling
@app.route('/example', methods=['GET', 'POST'])
def demo():
	if request.method == "POST":
		if 'section' in request.form:
			if request.form['section'] == "startAuth":
				attempted_username = request.form['username']
				if attempted_username == "akovesdy":
					data = {
						"username" : attempted_username,
						"apikey" : "",
						"ipaddress" : request.remote_addr,
					}
					return redirect(url_for('webAuthenticateUser', data=data))		
	elif request.method == "GET":
		if 'section' in request.form:
			if request.form['section'] == "checkAuth":
				user_id = request.form['user_id']
		else:
			return render_template('example.html')