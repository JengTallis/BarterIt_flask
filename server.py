#!/usr/bin/env python2.7

import thread
import os
from sqlalchemy import *
from sqlalchemy.pool import NullPool
from flask import Flask, request, render_template, g, redirect, Response

tmpl_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')
app = Flask(__name__, template_folder=tmpl_dir)

DB_USER = "jsp2201"
DB_PASSWORD = "68o5h3c9"

DB_SERVER = "w4111.cisxo09blonu.us-east-1.rds.amazonaws.com"

DATABASEURI = "postgresql://"+DB_USER+":"+DB_PASSWORD+"@"+DB_SERVER+"/w4111"

engine = create_engine(DATABASEURI)

engine.execute("DROP TABLE IF EXISTS Belongs_to;")
engine.execute("DROP TABLE IF EXISTS Items;")
engine.execute("DROP TABLE IF EXISTS Bundles;")
engine.execute("DROP TABLE IF EXISTS Wants;")
engine.execute("DROP TABLE IF EXISTS Categories;")
engine.execute("DROP TABLE IF EXISTS Lives_in;")
engine.execute("DROP TABLE IF EXISTS ZIPs;")
engine.execute("DROP TABLE IF EXISTS Users;")

engine.execute("""
CREATE TABLE Users(
 username VARCHAR(255)PRIMARY KEY,
 password VARCHAR(255)NOT NULL);""")

engine.execute("""
CREATE TABLE ZIPs(
 code VARCHAR(255)PRIMARY KEY);""")

engine.execute("""
CREATE TABLE Lives_in(
 username VARCHAR(255)REFERENCES Users(username),
 ZIP_code VARCHAR(255)REFERENCES ZIPs(code),
 PRIMARY KEY(username,ZIP_code));""")

engine.execute("""
CREATE TABLE Categories(
 name VARCHAR(255)PRIMARY KEY);""")

engine.execute("""
CREATE TABLE Wants(
 username VARCHAR(255)REFERENCES Users(username),
 category_name VARCHAR(255)REFERENCES Categories(name),
 PRIMARY KEY(username,category_name));""")

engine.execute("""
CREATE TABLE Bundles(
 ID INT PRIMARY KEY,
 lister VARCHAR(255)NOT NULL REFERENCES Users(username),
 name VARCHAR(255)NOT NULL,
 listening BOOLEAN NOT NULL,
 instructions text,
 server INT REFERENCES Bundles(ID),
 accepted BOOLEAN NOT NULL,
 stamp TIMESTAMPTZ,
 rating INT CHECK(1<=rating AND rating<=5),
 comment TEXT,
 unseen BOOLEAN NOT NULL);""")

engine.execute("""
CREATE TABLE Items(
 bundle_ID INT REFERENCES Bundles(ID),
 name VARCHAR(255),
 description TEXT NOT NULL,
 PRIMARY KEY(bundle_ID,name));""")

engine.execute("""
CREATE TABLE Belongs_to(
 bundle_ID INT,
 item_name VARCHAR(255),
 FOREIGN KEY(bundle_ID,item_name)REFERENCES Items(bundle_ID,name),
 category_name VARCHAR(255)REFERENCES Categories(name),
 PRIMARY KEY(bundle_ID,item_name,category_name));""")

lock=thread.allocate_lock()
next_bundle_ID=0

@app.before_request
def before_request():
  lock.acquire()
  try:
    g.conn = engine.connect()
  except:
    print "uh oh, problem connecting to database"
    import traceback; traceback.print_exc()
    g.conn = None

@app.teardown_request
def teardown_request(exception):
  try:
    g.conn.close()
  except Exception as e:
    pass
  lock.release()

@app.route("/")
def index():
 return render_template("index.html")

def invalid_string(string):
 return not string or"/"in string or"\\"in string

@app.route("/signup")
def signup():
 username=request.args.get("username")
 if invalid_string(username):
  return render_template("invalid_username.html",username=username)
 password=request.args.get("password")
 if invalid_string(password):
  return render_template("invalid_password.html",password=password)
 if g.conn.execute(text("SELECT EXISTS(SELECT*FROM Users WHERE username=:username);"),username=username).scalar():
  return render_template("duplicate_username.html",username=username)
 g.conn.execute(text("INSERT INTO Users VALUES(:username,:password);"),username=username,password=password)
 return redirect("/profile/"+username+"/"+password)

def invalid(username,password):
 return g.conn.execute(text("SELECT NOT EXISTS(SELECT*FROM Users WHERE username=:username AND password=:password);"),username=username,password=password).scalar()

def invalid_private(username,password,bundle_ID):
 return invalid(username,password)or g.conn.execute(text("SELECT NOT EXISTS(SELECT*FROM Bundles WHERE lister=:username AND ID=:bundle_ID AND NOT listening AND server IS NULL);"),username=username,bundle_ID=bundle_ID).scalar()

def invalid_item(username,password,bundle_ID,item_name):
 return invalid_private(username,password,bundle_ID)or g.conn.execute(text("SELECT NOT EXISTS(SELECT*FROM Items WHERE bundle_ID=:bundle_ID AND name=:item_name);"),bundle_ID=bundle_ID,item_name=item_name).scalar()

def invalid_belongs_to(username,password,bundle_ID,item_name,category_name):
 return invalid_item(username,password,bundle_ID,item_name)or g.conn.execute(text("SELECT NOT EXISTS(SELECT*FROM Belongs_to WHERE bundle_ID=:bundle_ID AND item_name=:item_name AND category_name=:category_name);"),bundle_ID=bundle_ID,item_name=item_name,category_name=category_name).scalar()

def invalid_lives_in(username,password,ZIP_code):
 return invalid(username,password)or g.conn.execute(text("SELECT NOT EXISTS(SELECT*FROM Lives_in WHERE username=:username AND ZIP_code=:ZIP_code);"),username=username,ZIP_code=ZIP_code).scalar()

def invalid_wants(username,password,category_name):
 return invalid(username,password)or g.conn.execute(text("SELECT NOT EXISTS(SELECT*FROM Wants WHERE username=:username AND category_name=:category_name);"),username=username,category_name=category_name).scalar()

def invalid_public(username,password,bundle_ID):
 return invalid(username,password)or g.conn.execute(text("""
SELECT NOT EXISTS(
 SELECT*FROM Bundles tmp0 WHERE tmp0.ID=:bundle_ID AND tmp0.lister=:username AND tmp0.listening AND NOT EXISTS(
  SELECT*FROM Bundles tmp1 WHERE tmp1.server=tmp0.ID AND tmp1.accepted));"""),username=username,bundle_ID=bundle_ID).scalar()

def invalid_exchanged(username,password,bundle_ID):
 return invalid(username,password)or g.conn.execute(text("""
SELECT NOT EXISTS(
 SELECT*FROM Bundles tmp0 WHERE tmp0.lister=:username AND tmp0.ID=:bundle_ID AND(tmp0.accepted OR EXISTS(
  SELECT*FROM Bundles tmp1 WHERE tmp1.server=:bundle_ID AND tmp1.accepted)));"""),username=username,bundle_ID=bundle_ID).scalar()

@app.route("/login")
def login():
 username=request.args.get("username")
 password=request.args.get("password")
 if invalid(username,password):
  return render_template("invalid_login.html")
 return redirect("/profile/"+username+"/"+password)

@app.route("/profile/<username>/<password>")
def profile(username,password):
 if invalid(username,password):
  return redirect("/")
 return render_template("profile.html",username=username,password=password)

@app.route("/private/<username>/<password>")
def private(username,password):
 if invalid(username,password):
  return redirect("/")
 bundles=[]
 for bundle in g.conn.execute(text("SELECT ID,name,unseen FROM Bundles WHERE lister=:username AND NOT listening AND server IS NULL;"),username=username):
  bundles.append(bundle)
 g.conn.execute(text("UPDATE Bundles SET unseen=FALSE WHERE lister=:username AND NOT listening AND server IS NULL;"),username=username)
 return render_template("private.html",username=username,password=password,bundles=bundles)

@app.route("/add_bundle/<username>/<password>")
def add_bundle(username,password):
 if invalid(username,password):
  return redirect("/")
 name=request.args.get("name")
 if not name:
  return render_template("empty_bundle.html",username=username,password=password)
 if g.conn.execute(text("""
SELECT EXISTS(
 SELECT*FROM Bundles tmp0 WHERE tmp0.lister=:username AND tmp0.name=:name AND NOT tmp0.accepted AND NOT EXISTS(
  SELECT*FROM Bundles tmp1 WHERE tmp1.server=tmp0.ID AND tmp1.accepted));"""),username=username,name=name).scalar():
  return render_template("duplicate_bundle.html",username=username,password=password,name=name)
 global next_bundle_ID
 bundle_ID=next_bundle_ID
 next_bundle_ID+=1
 g.conn.execute(text("INSERT INTO Bundles VALUES(:bundle_ID,:username,:name,FALSE,NULL,NULL,FALSE,NULL,NULL,NULL,FALSE);"),bundle_ID=bundle_ID,username=username,name=name)
 return redirect("/private_bundle/"+username+"/"+password+"/"+str(bundle_ID))

@app.route("/rename_bundle/<username>/<password>/<bundle_ID>")
def rename_bundle(username,password,bundle_ID):
 if invalid_private(username,password,bundle_ID):
  return redirect("/")
 name=request.args.get("name")
 if not name:
  return render_template("empty_bundle_re.html",username=username,password=password)
 if g.conn.execute(text("""
SELECT EXISTS(
 SELECT*FROM Bundles tmp0 WHERE tmp0.lister=:username AND tmp0.name=:name AND NOT tmp0.accepted AND NOT EXISTS(
  SELECT*FROM Bundles tmp1 WHERE tmp1.server=tmp0.ID AND tmp1.accepted));"""),username=username,name=name).scalar():
  return render_template("duplicate_bundle_re.html",username=username,password=password,bundle_ID=bundle_ID,name=name)
 g.conn.execute(text("UPDATE Bundles SET name=:name WHERE ID=:bundle_ID;"),bundle_ID=bundle_ID,name=name)
 return redirect("/private_bundle/"+username+"/"+password+"/"+bundle_ID)

@app.route("/remove_bundle/<username>/<password>/<bundle_ID>")
def remove_bundle(username,password,bundle_ID):
 if invalid_private(username,password,bundle_ID):
  return redirect("/")
 g.conn.execute(text("DELETE FROM Belongs_to WHERE bundle_ID=:bundle_ID;"),bundle_ID=bundle_ID)
 g.conn.execute(text("DELETE FROM Items WHERE bundle_ID=:bundle_ID;"),bundle_ID=bundle_ID)
 g.conn.execute(text("DELETE FROM Bundles WHERE ID=:bundle_ID;"),bundle_ID=bundle_ID)
 return redirect("/private/"+username+"/"+password)

@app.route("/private_bundle/<username>/<password>/<bundle_ID>")
def private_bundle(username,password,bundle_ID):
 if invalid_private(username,password,bundle_ID):
  return redirect("/")
 return render_template("private_bundle.html",username=username,password=password,bundle_ID=bundle_ID,**g.conn.execute(text("SELECT name,instructions FROM Bundles WHERE ID=:bundle_ID;"),bundle_ID=bundle_ID).first())

@app.route("/items/<username>/<password>/<bundle_ID>")
def items(username,password,bundle_ID):
 if invalid_private(username,password,bundle_ID):
  return redirect("/")
 item_names=[]
 for item in g.conn.execute(text("SELECT name FROM Items WHERE bundle_ID=:bundle_ID"),bundle_ID=bundle_ID):
  item_names.append(item['name'])
 return render_template("items.html",username=username,password=password,bundle_ID=bundle_ID,item_names=item_names,**g.conn.execute(text("SELECT name FROM Bundles WHERE ID=:bundle_ID;"),bundle_ID=bundle_ID).first())

@app.route("/item/<username>/<password>/<bundle_ID>/<item_name>")
def item(username,password,bundle_ID,item_name):
 if invalid_item(username,password,bundle_ID,item_name):
  return redirect("/")
 return render_template("item.html",username=username,password=password,bundle_ID=bundle_ID,item_name=item_name,**dict(g.conn.execute(text("SELECT description FROM Items WHERE bundle_ID=:bundle_ID AND name=:item_name;"),bundle_ID=bundle_ID,item_name=item_name).first().items()+g.conn.execute(text("SELECT name FROM Bundles WHERE ID=:bundle_ID;"),bundle_ID=bundle_ID).first().items()))

@app.route("/add_item/<username>/<password>/<bundle_ID>")
def add_item(username,password,bundle_ID):
 if invalid_private(username,password,bundle_ID):
  return redirect("/")
 name=request.args.get("name")
 if invalid_string(name):
  return render_template("invalid_item.html",username=username,password=password,bundle_ID=bundle_ID,name=name)
 if g.conn.execute(text("SELECT EXISTS(SELECT*FROM Items WHERE bundle_ID=:bundle_ID AND name=:name);"),bundle_ID=bundle_ID,name=name).scalar():
  return render_template("duplicate_item.html",username=username,password=password,bundle_ID=bundle_ID,name=name)
 description=request.args.get("description")
 g.conn.execute(text("INSERT INTO Items VALUES(:bundle_ID,:name,:description);"),bundle_ID=bundle_ID,name=name,description=description)
 return redirect("/item/"+username+"/"+password+"/"+bundle_ID+"/"+name)

@app.route("/rename_item/<username>/<password>/<bundle_ID>/<item_name>")
def rename_item(username,password,bundle_ID,item_name):
 if invalid_item(username,password,bundle_ID,item_name):
  return redirect("/")
 name=request.args.get("name")
 if invalid_string(name):
  return render_template("invalid_item_re.html",username=username,password=password,bundle_ID=bundle_ID,item_name=item_name,name=name)
 if g.conn.execute(text("SELECT EXISTS(SELECT*FROM Items WHERE bundle_ID=:bundle_ID AND name=:name);"),bundle_ID=bundle_ID,name=name).scalar():
  return render_template("duplicate_item_re.html",username=username,password=password,bundle_ID=bundle_ID,item_name=item_name,name=name)
 g.conn.execute(text("INSERT INTO Items(SELECT :bundle_ID,:name,description FROM Items WHERE bundle_ID=:bundle_ID AND name=:item_name);"),bundle_ID=bundle_ID,item_name=item_name,name=name)
 g.conn.execute(text("UPDATE Belongs_to SET item_name=:name WHERE bundle_ID=:bundle_ID AND item_name=:item_name;"),bundle_ID=bundle_ID,item_name=item_name,name=name)
 g.conn.execute(text("DELETE FROM Items WHERE bundle_ID=:bundle_ID AND name=:item_name;"),bundle_ID=bundle_ID,item_name=item_name)
 return redirect("/item/"+username+"/"+password+"/"+bundle_ID+"/"+name)

@app.route("/description/<username>/<password>/<bundle_ID>/<item_name>")
def description(username,password,bundle_ID,item_name):
 if invalid_item(username,password,bundle_ID,item_name):
  return redirect("/")
 description=request.args.get("description")
 g.conn.execute(text("UPDATE Items SET description=:description WHERE bundle_ID=:bundle_ID AND name=:item_name;"),bundle_ID=bundle_ID,item_name=item_name,description=description)
 return redirect("/item/"+username+"/"+password+"/"+bundle_ID+"/"+item_name)

@app.route("/remove_item/<username>/<password>/<bundle_ID>/<item_name>")
def remove_item(username,password,bundle_ID,item_name):
 if invalid_item(username,password,bundle_ID,item_name):
  return redirect("/")
 g.conn.execute(text("DELETE FROM Belongs_to WHERE bundle_ID=:bundle_ID AND item_name=:item_name;"),bundle_ID=bundle_ID,item_name=item_name)
 g.conn.execute(text("DELETE FROM Items WHERE bundle_ID=:bundle_ID AND name=:item_name;"),bundle_ID=bundle_ID,item_name=item_name)
 return redirect("/items/"+username+"/"+password+"/"+bundle_ID)

@app.route("/belongs_to/<username>/<password>/<bundle_ID>/<item_name>")
def belongs_to(username,password,bundle_ID,item_name):
 if invalid_item(username,password,bundle_ID,item_name):
  return redirect("/")
 categories=[]
 for belongs_to in g.conn.execute(text("SELECT category_name FROM Belongs_to WHERE bundle_ID=:bundle_ID AND item_name=:item_name;"),bundle_ID=bundle_ID,item_name=item_name):
  categories.append(belongs_to["category_name"])
 return render_template("belongs_to.html",username=username,password=password,bundle_ID=bundle_ID,item_name=item_name,categories=categories,**g.conn.execute(text("SELECT name FROM Bundles WHERE ID=:bundle_ID;"),bundle_ID=bundle_ID).first())

@app.route("/add_belongs_to/<username>/<password>/<bundle_ID>/<item_name>")
def add_belongs_to(username,password,bundle_ID,item_name):
 if invalid_item(username,password,bundle_ID,item_name):
  return redirect("/")
 name=request.args.get("name")
 if invalid_string(name):
  return render_template("invalid_belongs_to.html",username=username,password=password,bundle_ID=bundle_ID,item_name=item_name,name=name)
 if g.conn.execute(text("SELECT EXISTS(SELECT*FROM Belongs_to WHERE bundle_ID=:bundle_ID AND item_name=:item_name AND category_name=:name);"),bundle_ID=bundle_ID,item_name=item_name,name=name).scalar():
  return render_template("/duplicate_belongs_to.html",username=username,password=password,bundle_ID=bundle_ID,item_name=item_name,name=name)
 if g.conn.execute(text("SELECT NOT EXISTS(SELECT*FROM Categories WHERE name=:name);"),name=name).scalar():
  g.conn.execute(text("INSERT INTO Categories VALUES(:name);"),name=name)
 g.conn.execute(text("INSERT INTO Belongs_to VALUES(:bundle_ID,:item_name,:name);"),bundle_ID=bundle_ID,item_name=item_name,name=name)
 return redirect("/belongs_to/"+username+"/"+password+"/"+bundle_ID+"/"+item_name)

@app.route("/remove_belongs_to/<username>/<password>/<bundle_ID>/<item_name>/<category_name>")
def remove_belongs_to(username,password,bundle_ID,item_name,category_name):
 if invalid_belongs_to(username,password,bundle_ID,item_name,category_name):
  return redirect("/")
 g.conn.execute(text("DELETE FROM Belongs_to WHERE bundle_ID=:bundle_ID AND item_name=:item_name AND category_name=:category_name;"),bundle_ID=bundle_ID,item_name=item_name,category_name=category_name)
 return redirect("/belongs_to/"+username+"/"+password+"/"+bundle_ID+"/"+item_name)

@app.route("/move/<username>/<password>/<bundle_ID>/<item_name>")
def move(username,password,bundle_ID,item_name):
 if invalid_item(username,password,bundle_ID,item_name):
  return redirect("/")
 bundles=[]
 for bundle in g.conn.execute(text("""
SELECT tmp0.ID,tmp0.name FROM Bundles tmp0 WHERE tmp0.lister=:username AND NOT tmp0.listening AND tmp0.server IS NULL AND NOT EXISTS(
 SELECT*FROM Items tmp1 WHERE tmp1.bundle_ID=tmp0.ID AND tmp1.name=:item_name);"""),username=username,item_name=item_name):
  bundles.append(bundle)
 return render_template("move.html",username=username,password=password,bundle_ID=bundle_ID,item_name=item_name,bundles=bundles,**g.conn.execute(text("SELECT name FROM Bundles WHERE ID=:bundle_ID;"),bundle_ID=bundle_ID).first())

@app.route("/move_to/<username>/<password>/<bundle_ID>/<item_name>/<destination>")
def move_to(username,password,bundle_ID,item_name,destination):
 if invalid_item(username,password,bundle_ID,item_name):
  return redirect("/")
 if invalid_private(username,password,destination):
  return redirect("/")
 if g.conn.execute(text("SELECT EXISTS(SELECT*FROM Items WHERE bundle_ID=:destination AND name=:item_name);"),item_name=item_name,destination=destination).scalar():
  return redirect("/")
 g.conn.execute(text("INSERT INTO Items VALUES(:destination,:item_name,:description);"),destination=destination,item_name=item_name,**g.conn.execute(text("SELECT description FROM Items WHERE bundle_ID=:bundle_ID AND name=:item_name;"),bundle_ID=bundle_ID,item_name=item_name).first())
 g.conn.execute(text("UPDATE Belongs_to SET bundle_ID=:destination WHERE bundle_ID=:bundle_ID AND item_name=:item_name;"),bundle_ID=bundle_ID,item_name=item_name,destination=destination)
 g.conn.execute(text("DELETE FROM Items WHERE bundle_ID=:bundle_ID AND name=:item_name;"),bundle_ID=bundle_ID,item_name=item_name)
 return redirect("/item/"+username+"/"+password+"/"+str(destination)+"/"+item_name)

@app.route("/moveall/<username>/<password>/<bundle_ID>")
def moveall(username,password,bundle_ID):
 if invalid_private(username,password,bundle_ID):
  return redirect("/")
 bundles=[]
 for bundle in g.conn.execute(text("""
SELECT tmp0.ID,tmp0.name FROM Bundles tmp0 WHERE tmp0.ID<>:bundle_ID AND tmp0.lister=:username AND NOT tmp0.listening AND tmp0.server IS NULL AND NOT EXISTS(
 SELECT*FROM Items tmp1,Items tmp2 WHERE tmp1.bundle_ID=tmp0.ID AND tmp2.bundle_ID=:bundle_ID AND tmp1.name=tmp2.name);"""),username=username,bundle_ID=bundle_ID):
  bundles.append(bundle)
 return render_template("moveall.html",username=username,password=password,bundle_ID=bundle_ID,bundles=bundles,**g.conn.execute(text("SELECT name FROM Bundles WHERE ID=:bundle_ID;"),bundle_ID=bundle_ID).first())

@app.route("/moveall_to/<username>/<password>/<bundle_ID>/<destination>")
def moveall_to(username,password,bundle_ID,destination):
 if invalid_private(username,password,bundle_ID):
  return redirect("/")
 if invalid_private(username,password,destination):
  return redirect("/")
 if g.conn.execute(text("SELECT EXISTS(SELECT*FROM Items tmp0,Items tmp1 WHERE tmp0.bundle_ID=:bundle_ID AND tmp1.bundle_ID=:destination AND tmp0.name=tmp1.name);"),bundle_ID=bundle_ID,destination=destination).scalar():
  return redirect("/")
 g.conn.execute(text("INSERT INTO Items(SELECT :destination,name,description FROM Items WHERE bundle_ID=:bundle_ID);"),bundle_ID=bundle_ID,destination=destination)
 g.conn.execute(text("UPDATE Belongs_to SET bundle_ID=:destination WHERE bundle_ID=:bundle_ID;"),bundle_ID=bundle_ID,destination=destination)
 g.conn.execute(text("DELETE FROM Items WHERE bundle_ID=:bundle_ID;"),bundle_ID=bundle_ID)
 return redirect("/items/"+username+"/"+password+"/"+destination)

@app.route("/lives_in/<username>/<password>")
def lives_in(username,password):
 if invalid(username,password):
  return redirect("/")
 codes=[]
 for ZIP in g.conn.execute(text("SELECT ZIP_code FROM Lives_in WHERE username=:username;"),username=username):
  codes.append(ZIP["zip_code"])
 return render_template("lives_in.html",username=username,password=password,codes=codes)

@app.route("/add_lives_in/<username>/<password>")
def add_lives_in(username,password):
 if invalid(username,password):
  return redirect("/")
 code=request.args.get("code")
 if invalid_string(code):
  return render_template("invalid_lives_in.html",username=username,password=password,code=code)
 if g.conn.execute(text("SELECT EXISTS(SELECT*FROM Lives_in WHERE username=:username AND ZIP_code=:code);"),username=username,code=code).scalar():
  return render_template("duplicate_lives_in.html",username=username,password=password,code=code)
 if g.conn.execute(text("SELECT NOT EXISTS(SELECT*FROM ZIPs WHERE code=:code);"),code=code).scalar():
  g.conn.execute(text("INSERT INTO ZIPs VALUES(:code);"),code=code)
 g.conn.execute(text("INSERT INTO Lives_in VALUES(:username,:code);"),username=username,code=code)
 return redirect("/lives_in/"+username+"/"+password)

@app.route("/remove_lives_in/<username>/<password>/<ZIP_code>")
def remove_lives_in(username,password,ZIP_code):
 if invalid_lives_in(username,password,ZIP_code):
  return redirect("/")
 g.conn.execute(text("DELETE FROM Lives_in WHERE username=:username AND ZIP_code=:ZIP_code;"),username=username,ZIP_code=ZIP_code)
 return redirect("/lives_in/"+username+"/"+password)

@app.route("/wants/<username>/<password>")
def wants(username,password):
 if invalid(username,password):
  return redirect("/")
 categories=[]
 for category in g.conn.execute(text("SELECT category_name FROM Wants WHERE username=:username;"),username=username):
  categories.append(category["category_name"])
 return render_template("wants.html",username=username,password=password,categories=categories)

@app.route("/add_wants/<username>/<password>")
def add_wants(username,password):
 if invalid(username,password):
  return redirect("/")
 name=request.args.get("name")
 if invalid_string(name):
  return render_template("invalid_wants.html",username=username,password=password,name=name)
 if g.conn.execute(text("SELECT EXISTS(SELECT*FROM Wants WHERE username=:username AND category_name=:name);"),username=username,name=name).scalar():
  return render_template("duplicate_wants.html",username=username,password=password,name=name)
 if g.conn.execute(text("SELECT NOT EXISTS(SELECT*FROM Categories WHERE name=:name);"),name=name).scalar():
  g.conn.execute(text("INSERT INTO Categories VALUES(:name);"),name=name)
 g.conn.execute(text("INSERT INTO Wants VALUES(:username,:name);"),username=username,name=name)
 return redirect("/wants/"+username+"/"+password)

@app.route("/remove_wants/<username>/<password>/<category_name>")
def remove_wants(username,password,category_name):
 if invalid_wants(username,password,category_name):
  return redirect("/")
 g.conn.execute(text("DELETE FROM Wants WHERE username=:username AND category_name=:category_name;"),username=username,category_name=category_name)
 return redirect("/wants/"+username+"/"+password)

@app.route("/username/<username>/<password>")
def username(username,password):
 if invalid(username,password):
  return redirect("/")
 new_username=request.args.get("username")
 if invalid_string(new_username):
  return render_template("invalid_username_re.html",username=username,password=password,new_username=new_username)
 if g.conn.execute(text("SELECT EXISTS(SELECT*FROM Users WHERE username=:new_username);"),new_username=new_username).scalar():
  return render_template("duplicate_username_re.html",username=username,password=password,new_username=new_username)
 g.conn.execute(text("INSERT INTO Users VALUES(:new_username,:password);"),new_username=new_username,password=password)
 g.conn.execute(text("UPDATE Bundles SET lister=:new_username WHERE lister=:username;"),username=username,new_username=new_username)
 g.conn.execute(text("UPDATE Wants SET username=:new_username WHERE username=:username;"),username=username,new_username=new_username)
 g.conn.execute(text("UPDATE Lives_in SET username=:new_username WHERE username=:username;"),username=username,new_username=new_username)
 g.conn.execute(text("DELETE FROM Users WHERE username=:username;"),username=username)
 return redirect("/profile/"+new_username+"/"+password)

@app.route("/password/<username>/<password>")
def password(username,password):
 if invalid(username,password):
  return redirect("/")
 new_password=request.args.get("password")
 if invalid_string(new_password):
  return render_template("invalid_password_re.html",username=username,password=password,new_password=new_password)
 g.conn.execute(text("UPDATE Users SET password=:new_password WHERE username=:username;"),username=username,new_password=new_password)
 return redirect("/profile/"+username+"/"+new_password)

@app.route("/publish/<username>/<password>/<bundle_ID>")
def publish(username,password,bundle_ID):
 if invalid_private(username,password,bundle_ID):
  return redirect("/")
 if g.conn.execute(text("SELECT NOT EXISTS(SELECT*FROM Items WHERE bundle_ID=:bundle_ID);"),bundle_ID=bundle_ID).scalar():
  return render_template("empty_publish.html",username=username,password=password,bundle_ID=bundle_ID)
 instructions=request.args.get("instructions")
 g.conn.execute(text("UPDATE Bundles SET listening=TRUE,instructions=:instructions WHERE ID=:bundle_ID;"),bundle_ID=bundle_ID,instructions=instructions)
 return redirect("/public_bundle/"+username+"/"+password+"/"+bundle_ID)

@app.route("/unpublish/<username>/<password>/<bundle_ID>")
def unpublish(username,password,bundle_ID):
 if invalid_public(username,password,bundle_ID):
  return redirect("/")
 g.conn.execute(text("UPDATE Bundles SET server=NULL WHERE server=:bundle_ID;"),bundle_ID=bundle_ID)
 global next_bundle_ID
 new_bundle_ID=next_bundle_ID
 next_bundle_ID+=1
 g.conn.execute(text("INSERT INTO Bundles(SELECT :new_bundle_ID,:username,name,FALSE,instructions,NULL,FALSE,NULL,NULL,NULL,FALSE FROM Bundles WHERE ID=:bundle_ID);"),username=username,bundle_ID=bundle_ID,new_bundle_ID=new_bundle_ID)
 g.conn.execute(text("INSERT INTO Items(SELECT :new_bundle_ID,name,description FROM Items WHERE bundle_ID=:bundle_ID);"),bundle_ID=bundle_ID,new_bundle_ID=new_bundle_ID)
 g.conn.execute(text("UPDATE Belongs_to SET bundle_ID=:new_bundle_ID WHERE bundle_ID=:bundle_ID;"),bundle_ID=bundle_ID,new_bundle_ID=new_bundle_ID)
 g.conn.execute(text("DELETE FROM Items WHERE bundle_ID=:bundle_ID;"),bundle_ID=bundle_ID)
 g.conn.execute(text("DELETE FROM Bundles WHERE ID=:bundle_ID;"),bundle_ID=bundle_ID)
 return redirect("/private_bundle/"+username+"/"+password+"/"+str(new_bundle_ID))

@app.route("/public/<username>/<password>")
def public(username,password):
 if invalid(username,password):
  return redirect("/")
 bundles=[]
 for bundle in g.conn.execute(text("""
SELECT ID,name FROM Bundles tmp0 WHERE tmp0.lister=:username AND tmp0.listening AND NOT EXISTS(
 SELECT*FROM Bundles tmp1 WHERE tmp1.server=tmp0.ID AND tmp1.accepted);"""),username=username):
  bundles.append(bundle)
 return render_template("public.html",username=username,password=password,bundles=bundles)

@app.route("/public_bundle/<username>/<password>/<bundle_ID>")
def public_bundle(username,password,bundle_ID):
 if invalid_public(username,password,bundle_ID):
  return redirect("/")
 return render_template("public_bundle.html",username=username,password=password,bundle_ID=bundle_ID,**dict(g.conn.execute(text("SELECT instructions FROM Bundles WHERE ID=:bundle_ID;"),bundle_ID=bundle_ID).first().items()+g.conn.execute(text("SELECT name FROM Bundles WHERE ID=:bundle_ID;"),bundle_ID=bundle_ID).first().items()))

@app.route("/clients/<username>/<password>/<bundle_ID>")
def clients(username,password,bundle_ID):
 if invalid_public(username,password,bundle_ID):
  return redirect("/")
 clients=[]
 for client in g.conn.execute(text("""
SELECT tmp0.lister,AVG(tmp0.rating)average_rating,(
 SELECT COUNT(*)FROM Bundles tmp2 WHERE tmp2.lister=tmp0.lister AND tmp2.rating IS NOT NULL)rating_count FROM Bundles tmp0 GROUP BY tmp0.lister HAVING EXISTS(
 SELECT*FROM Bundles tmp1 WHERE tmp1.lister=tmp0.lister AND tmp1.server=:bundle_ID)ORDER BY average_rating DESC NULLS LAST,rating_count DESC;"""),bundle_ID=bundle_ID):
  clients.append({"lister":client["lister"],"average_rating":float(str(client["average_rating"]))if client["average_rating"]else None,"rating_count":client["rating_count"]})
 return render_template("clients.html",username=username,password=password,bundle_ID=bundle_ID,clients=clients,**g.conn.execute(text("SELECT name FROM Bundles WHERE ID=:bundle_ID;"),bundle_ID=bundle_ID).first())

@app.route("/client/<username>/<password>/<bundle_ID>/<client>")
def client(username,password,bundle_ID,client):
 if invalid_public(username,password,bundle_ID):
  return redirect("/")
 bundles=[]
 for bundle in g.conn.execute(text("SELECT ID,name FROM Bundles WHERE lister=:client AND server=:bundle_ID;"),bundle_ID=bundle_ID,client=client):
  bundles.append(bundle)
 return render_template("client.html",username=username,password=password,bundle_ID=bundle_ID,client=client,bundles=bundles,**g.conn.execute(text("SELECT name FROM Bundles WHERE ID=:bundle_ID;"),bundle_ID=bundle_ID).first())

@app.route("/client_bundle/<username>/<password>/<bundle_ID>/<client>/<client_bundle>")
def client_bundle(username,password,bundle_ID,client,client_bundle):
 if invalid_public(username,password,bundle_ID):
  return redirect("/")
 if g.conn.execute(text("SELECT NOT EXISTS(SELECT*FROM Bundles WHERE lister=:client AND ID=:client_bundle AND server=:bundle_ID);"),bundle_ID=bundle_ID,client=client,client_bundle=client_bundle).scalar():
  return render_template("client_bundle_unavailable.html",username=username,password=password,bundle_ID=bundle_ID,client=client)
 return render_template("client_bundle.html",username=username,password=password,bundle_ID=bundle_ID,client=client,client_bundle=client_bundle,**g.conn.execute(text("SELECT name FROM Bundles WHERE ID=:client_bundle;"),client_bundle=client_bundle).first())

@app.route("/accept_offer/<username>/<password>/<bundle_ID>/<client>/<client_bundle>")
def accept_offer(username,password,bundle_ID,client,client_bundle):
 if invalid_public(username,password,bundle_ID):
  return redirect("/")
 if g.conn.execute(text("""
SELECT NOT EXISTS(
 SELECT*FROM Bundles WHERE ID=:client_bundle AND server=:bundle_ID);"""),bundle_ID=bundle_ID,client_bundle=client_bundle).scalar():
  return render_template("accept_offer_unavailable.html",username=username,password=password,bundle_ID=bundle_ID,client=client)
 g.conn.execute(text("UPDATE Bundles SET accepted=TRUE,stamp=CURRENT_TIMESTAMP,unseen=TRUE WHERE ID=:client_bundle;"),client_bundle=client_bundle)
 g.conn.execute(text("UPDATE Bundles SET unseen=TRUE WHERE ID=:bundle_ID;"),bundle_ID=bundle_ID)
 return redirect("/exchanged/"+username+"/"+password)

@app.route("/reject_offer/<username>/<password>/<bundle_ID>/<client>/<client_bundle>")
def reject_offer(username,password,bundle_ID,client,client_bundle):
 if invalid_public(username,password,bundle_ID):
  return redirect("/")
 if g.conn.execute(text("""
SELECT EXISTS(
 SELECT*FROM Bundles WHERE ID=:client_bundle AND server=:bundle_ID);"""),bundle_ID=bundle_ID,client_bundle=client_bundle).scalar():
  g.conn.execute(text("UPDATE Bundles SET server=NULL,unseen=TRUE WHERE ID=:client_bundle;"),client_bundle=client_bundle)
 return redirect("/client/"+username+"/"+password+"/"+bundle_ID+"/"+client)

@app.route("/servers/<username>/<password>/<bundle_ID>")
def servers(username,password,bundle_ID):
 if invalid_private(username,password,bundle_ID):
  return redirect("/")
 servers=[]
 for server in g.conn.execute(text("""
SELECT tmp0.lister,AVG(tmp0.rating)average_rating,(
 SELECT COUNT(*)FROM Bundles tmpB WHERE tmpB.lister=tmp0.lister AND tmpB.rating IS NOT NULL)rating_count FROM Bundles tmp0 GROUP BY tmp0.lister HAVING EXISTS(
 SELECT*FROM Bundles tmp1 WHERE tmp1.lister=tmp0.lister AND tmp1.listening AND NOT EXISTS(
  SELECT*FROM Bundles tmp2 WHERE tmp2.server=tmp1.ID AND tmp2.accepted)AND EXISTS(
  SELECT*FROM Items tmp3 WHERE tmp3.bundle_ID=tmp1.ID AND EXISTS(
   SELECT*FROM Belongs_to tmp4 WHERE tmp4.bundle_ID=tmp3.bundle_ID AND tmp4.item_name=tmp3.name AND EXISTS(
    SELECT*FROM Wants tmp5 WHERE tmp5.username=:username AND tmp5.category_name=tmp4.category_name))))AND EXISTS(
 SELECT*FROM Items tmp6 WHERE tmp6.bundle_ID=:bundle_ID AND EXISTS(
  SELECT*FROM Belongs_to tmp7 WHERE tmp7.bundle_ID=:bundle_ID AND tmp7.item_name=tmp6.name AND EXISTS(
   SELECT*FROM Wants tmp8 WHERE tmp8.username=tmp0.lister AND tmp8.category_name=tmp7.category_name)))AND EXISTS(
 SELECT*FROM Lives_in tmp9,Lives_in tmpA WHERE tmp9.username=:username AND tmpA.username=tmp0.lister AND tmp9.ZIP_code=tmpA.ZIP_code)ORDER BY average_rating DESC NULLS LAST,rating_count DESC;"""),username=username,bundle_ID=bundle_ID):
  servers.append({"lister":server["lister"],"average_rating":float(str(server["average_rating"]))if server["average_rating"]else None,"rating_count":server["rating_count"]})
 return render_template("servers.html",username=username,password=password,bundle_ID=bundle_ID,servers=servers,**g.conn.execute(text("SELECT name FROM Bundles WHERE ID=:bundle_ID;"),bundle_ID=bundle_ID).first())

@app.route("/server/<username>/<password>/<bundle_ID>/<server>")
def server(username,password,bundle_ID,server):
 if invalid_private(username,password,bundle_ID):
  return redirect("/")
 bundles=[]
 for bundle in g.conn.execute(text("""
SELECT tmp0.ID,tmp0.name FROM Bundles tmp0 WHERE tmp0.lister=:server AND tmp0.listening AND NOT EXISTS(
 SELECT*FROM Bundles tmp1 WHERE tmp1.server=tmp0.ID AND tmp1.accepted)AND EXISTS(
 SELECT*FROM Items tmp2 WHERE tmp2.bundle_ID=tmp0.ID AND EXISTS(
  SELECT*FROM Belongs_to tmp3 WHERE tmp3.bundle_ID=tmp2.bundle_ID AND tmp3.item_name=tmp2.name AND EXISTS(
   SELECT*FROM Wants tmp4 WHERE tmp4.username=:username AND tmp4.category_name=tmp3.category_name)))"""),username=username,server=server):
  bundles.append(bundle)
 return render_template("server.html",username=username,password=password,bundle_ID=bundle_ID,server=server,bundles=bundles,**g.conn.execute(text("SELECT name FROM Bundles WHERE ID=:bundle_ID;"),bundle_ID=bundle_ID).first())

@app.route("/server_bundle/<username>/<password>/<bundle_ID>/<server>/<server_bundle>")
def server_bundle(username,password,bundle_ID,server,server_bundle):
 if invalid_private(username,password,bundle_ID):
  return redirect("/")
 if g.conn.execute(text("""
SELECT NOT EXISTS(
 SELECT*FROM Bundles tmp0 WHERE tmp0.ID=:server_bundle AND tmp0.listening AND NOT EXISTS(
  SELECT*FROM Bundles tmp1 WHERE tmp1.server=:server_bundle AND tmp1.accepted));"""),server=server,server_bundle=server_bundle).scalar():
  return render_template("server_bundle_unavailable.html",username=username,password=password,bundle_ID=bundle_ID,server=server)
 return render_template("server_bundle.html",username=username,password=password,bundle_ID=bundle_ID,server=server,server_bundle=server_bundle,**dict(g.conn.execute(text("SELECT instructions FROM Bundles WHERE ID=:server_bundle"),server_bundle=server_bundle).first().items()+g.conn.execute(text("SELECT name FROM Bundles WHERE ID=:server_bundle;"),server_bundle=server_bundle).first().items()))

@app.route("/make_offer/<username>/<password>/<bundle_ID>/<server>/<server_bundle>")
def make_offer(username,password,bundle_ID,server,server_bundle):
 if invalid_private(username,password,bundle_ID):
  return redirect("/")
 if g.conn.execute(text("""
SELECT NOT EXISTS(
 SELECT*FROM Bundles tmp0 WHERE tmp0.ID=:server_bundle AND tmp0.listening AND NOT EXISTS(
  SELECT*FROM Bundles tmp1 WHERE tmp1.server=:server_bundle AND tmp1.accepted));"""),server=server,server_bundle=server_bundle).scalar():
  return render_template("make_offer_unavailable.html",username=username,password=password,bundle_ID=bundle_ID,server=server)
 if g.conn.execute(text("SELECT NOT EXISTS(SELECT*FROM Items WHERE bundle_ID=:bundle_ID);"),bundle_ID=bundle_ID).scalar():
  return render_template("empty_offer.html",username=username,password=password,bundle_ID=bundle_ID,server=server,server_bundle=server_bundle)
 g.conn.execute(text("UPDATE Bundles SET server=:server_bundle WHERE ID=:bundle_ID;"),bundle_ID=bundle_ID,server_bundle=server_bundle)
 return redirect("/offered_bundle/"+username+"/"+password+"/"+bundle_ID)

@app.route("/offered/<username>/<password>")
def offered(username,password):
 if invalid(username,password):
  return redirect("/")
 bundles=[]
 for bundle in g.conn.execute(text("SELECT ID,name FROM Bundles WHERE lister=:username AND server IS NOT NULL AND NOT accepted;"),username=username):
  bundles.append(bundle)
 return render_template("offered.html",username=username,password=password,bundles=bundles)

@app.route("/offered_bundle/<username>/<password>/<bundle_ID>")
def offered_bundle(username,password,bundle_ID):
 if invalid(username,password):
  return redirect("/")
 if g.conn.execute(text("SELECT NOT EXISTS(SELECT*FROM Bundles WHERE lister=:username AND ID=:bundle_ID);"),username=username,bundle_ID=bundle_ID).scalar():
  return redirect("/")
 if g.conn.execute(text("SELECT EXISTS(SELECT*FROM Bundles WHERE ID=:bundle_ID AND server IS NULL);"),bundle_ID=bundle_ID).scalar():
  return redirect("/private/"+username+"/"+password)
 if g.conn.execute(text("SELECT EXISTS(SELECT*FROM Bundles WHERE ID=:bundle_ID AND accepted);"),bundle_ID=bundle_ID).scalar():
  return redirect("/exchanged/"+username+"/"+password)
 return render_template("offered_bundle.html",username=username,password=password,bundle_ID=bundle_ID,**dict(g.conn.execute(text("""
SELECT lister,ID,name,instructions FROM Bundles tmp0 WHERE EXISTS(
 SELECT*FROM Bundles tmp1 WHERE tmp1.ID=:bundle_ID AND tmp1.server=tmp0.ID)"""),bundle_ID=bundle_ID).first().items()+g.conn.execute(text("SELECT name offered FROM Bundles WHERE ID=:bundle_ID;"),bundle_ID=bundle_ID).first().items()))

@app.route("/retract_offer/<username>/<password>/<bundle_ID>")
def retract_offer(username,password,bundle_ID):
 if invalid(username,password):
  return redirect("/")
 if g.conn.execute(text("SELECT NOT EXISTS(SELECT*FROM Bundles WHERE lister=:username AND ID=:bundle_ID);"),username=username,bundle_ID=bundle_ID).scalar():
  return redirect("/")
 if g.conn.execute(text("SELECT EXISTS(SELECT*FROM Bundles WHERE ID=:bundle_ID AND server IS NULL);"),bundle_ID=bundle_ID).scalar():
  g.conn.execute(text("UPDATE Bundles SET unseen=FALSE WHERE ID=:bundle_ID;"),bundle_ID=bundle_ID)
  return redirect("/private_bundle/"+username+"/"+password+"/"+bundle_ID)
 if g.conn.execute(text("SELECT EXISTS(SELECT*FROM Bundles WHERE ID=:bundle_ID AND accepted);"),bundle_ID=bundle_ID).scalar():
  return render_template("retract_offer_unavailable.html",username=username,password=password)
 global next_bundle_ID
 new_bundle_ID=next_bundle_ID
 next_bundle_ID+=1
 g.conn.execute(text("INSERT INTO Bundles(SELECT :new_bundle_ID,:username,name,FALSE,instructions,NULL,FALSE,NULL,NULL,NULL,FALSE FROM Bundles WHERE ID=:bundle_ID);"),username=username,bundle_ID=bundle_ID,new_bundle_ID=new_bundle_ID)
 g.conn.execute(text("INSERT INTO Items(SELECT :new_bundle_ID,name,description FROM Items WHERE bundle_ID=:bundle_ID);"),bundle_ID=bundle_ID,new_bundle_ID=new_bundle_ID)
 g.conn.execute(text("UPDATE Belongs_to SET bundle_ID=:new_bundle_ID WHERE bundle_ID=:bundle_ID;"),bundle_ID=bundle_ID,new_bundle_ID=new_bundle_ID)
 g.conn.execute(text("DELETE FROM Items WHERE bundle_ID=:bundle_ID;"),bundle_ID=bundle_ID)
 g.conn.execute(text("DELETE FROM Bundles WHERE ID=:bundle_ID;"),bundle_ID=bundle_ID)
 return redirect("/private_bundle/"+username+"/"+password+"/"+str(new_bundle_ID))

@app.route("/offered_items_0/<username>/<password>/<bundle_ID>")
def offered_items_0(username,password,bundle_ID):
 if invalid(username,password):
  return redirect("/")
 if g.conn.execute(text("SELECT NOT EXISTS(SELECT*FROM Bundles WHERE lister=:username AND ID=:bundle_ID);"),username=username,bundle_ID=bundle_ID).scalar():
  return redirect("/")
 if g.conn.execute(text("SELECT EXISTS(SELECT*FROM Bundles WHERE ID=:bundle_ID AND server IS NULL);"),bundle_ID=bundle_ID).scalar():
  return redirect("/private/"+username+"/"+password)
 if g.conn.execute(text("SELECT EXISTS(SELECT*FROM Bundles WHERE ID=:bundle_ID AND accepted);"),bundle_ID=bundle_ID).scalar():
  return redirect("/exchanged/"+username+"/"+password)
 items=[]
 for item in g.conn.execute(text("SELECT name FROM Items WHERE bundle_ID=:bundle_ID;"),bundle_ID=bundle_ID):
  items.append(item["name"])
 return render_template("offered_items_0.html",username=username,password=password,bundle_ID=bundle_ID,items=items,**g.conn.execute(text("SELECT name FROM Bundles WHERE ID=:bundle_ID;"),bundle_ID=bundle_ID).first())

@app.route("/offered_item_0/<username>/<password>/<bundle_ID>/<item_name>")
def offered_item_0(username,password,bundle_ID,item_name):
 if invalid(username,password):
  return redirect("/")
 if g.conn.execute(text("SELECT NOT EXISTS(SELECT*FROM Bundles WHERE lister=:username AND ID=:bundle_ID);"),username=username,bundle_ID=bundle_ID).scalar():
  return redirect("/")
 if g.conn.execute(text("SELECT NOT EXISTS(SELECT*FROM Items WHERE bundle_ID=:bundle_ID AND name=:item_name);"),bundle_ID=bundle_ID,item_name=item_name).scalar():
  return redirect("/")
 if g.conn.execute(text("SELECT EXISTS(SELECT*FROM Bundles WHERE ID=:bundle_ID AND server IS NULL);"),bundle_ID=bundle_ID).scalar():
  return redirect("/private/"+username+"/"+password)
 if g.conn.execute(text("SELECT EXISTS(SELECT*FROM Bundles WHERE ID=:bundle_ID AND accepted);"),bundle_ID=bundle_ID).scalar():
  return redirect("/exchanged/"+username+"/"+password)
 return render_template("offered_item_0.html",username=username,password=password,bundle_ID=bundle_ID,item_name=item_name,**dict(g.conn.execute(text("SELECT description FROM Items WHERE bundle_ID=:bundle_ID AND name=:item_name;"),bundle_ID=bundle_ID,item_name=item_name).first().items()+g.conn.execute(text("SELECT name FROM Bundles WHERE ID=:bundle_ID;"),bundle_ID=bundle_ID).first().items()))

@app.route("/offered_belongs_to_0/<username>/<password>/<bundle_ID>/<item_name>")
def offered_belongs_to_0(username,password,bundle_ID,item_name):
 if invalid(username,password):
  return redirect("/")
 if g.conn.execute(text("SELECT NOT EXISTS(SELECT*FROM Bundles WHERE lister=:username AND ID=:bundle_ID);"),username=username,bundle_ID=bundle_ID).scalar():
  return redirect("/")
 if g.conn.execute(text("SELECT NOT EXISTS(SELECT*FROM Items WHERE bundle_ID=:bundle_ID AND name=:item_name);"),bundle_ID=bundle_ID,item_name=item_name).scalar():
  return redirect("/")
 if g.conn.execute(text("SELECT EXISTS(SELECT*FROM Bundles WHERE ID=:bundle_ID AND server IS NULL);"),bundle_ID=bundle_ID).scalar():
  return redirect("/private/"+username+"/"+password)
 if g.conn.execute(text("SELECT EXISTS(SELECT*FROM Bundles WHERE ID=:bundle_ID AND accepted);"),bundle_ID=bundle_ID).scalar():
  return redirect("/exchanged/"+username+"/"+password)
 categories=[]
 for category in g.conn.execute(text("SELECT category_name FROM Belongs_to WHERE bundle_ID=:bundle_ID AND item_name=:item_name;"),bundle_ID=bundle_ID,item_name=item_name):
  categories.append(category["category_name"])
 return render_template("offered_belongs_to_0.html",username=username,password=password,bundle_ID=bundle_ID,item_name=item_name,categories=categories,**g.conn.execute(text("SELECT name FROM Bundles WHERE ID=:bundle_ID;"),bundle_ID=bundle_ID).first())

@app.route("/offered_items_1/<username>/<password>/<bundle_ID>/<server_bundle>")
def offered_items_1(username,password,bundle_ID,server_bundle):
 if invalid(username,password):
  return redirect("/")
 if g.conn.execute(text("SELECT NOT EXISTS(SELECT*FROM Bundles WHERE lister=:username AND ID=:bundle_ID);"),username=username,bundle_ID=bundle_ID).scalar():
  return redirect("/")
 if g.conn.execute(text("SELECT EXISTS(SELECT*FROM Bundles WHERE ID=:bundle_ID AND server IS NULL);"),bundle_ID=bundle_ID).scalar():
  return redirect("/private/"+username+"/"+password)
 if g.conn.execute(text("SELECT NOT EXISTS(SELECT*FROM Bundles WHERE ID=:bundle_ID AND server=:server_bundle);"),bundle_ID=bundle_ID,server_bundle=server_bundle).scalar():
  return redirect("/")
 if g.conn.execute(text("SELECT EXISTS(SELECT*FROM Bundles WHERE ID=:bundle_ID AND accepted);"),bundle_ID=bundle_ID).scalar():
  return redirect("/exchanged/"+username+"/"+password)
 items=[]
 for item in g.conn.execute(text("SELECT name FROM Items WHERE bundle_ID=:server_bundle;"),server_bundle=server_bundle):
  items.append(item["name"])
 return render_template("offered_items_1.html",username=username,password=password,bundle_ID=bundle_ID,server_bundle=server_bundle,items=items,**g.conn.execute(text("SELECT name,lister FROM Bundles WHERE ID=:server_bundle;"),server_bundle=server_bundle).first())

@app.route("/offered_item_1/<username>/<password>/<bundle_ID>/<server_bundle>/<item_name>")
def offered_item_1(username,password,bundle_ID,server_bundle,item_name):
 if invalid(username,password):
  return redirect("/")
 if g.conn.execute(text("SELECT NOT EXISTS(SELECT*FROM Bundles WHERE lister=:username AND ID=:bundle_ID);"),username=username,bundle_ID=bundle_ID).scalar():
  return redirect("/")
 if g.conn.execute(text("SELECT EXISTS(SELECT*FROM Bundles WHERE ID=:bundle_ID AND server IS NULL);"),bundle_ID=bundle_ID).scalar():
  return redirect("/private/"+username+"/"+password)
 if g.conn.execute(text("SELECT NOT EXISTS(SELECT*FROM Bundles WHERE ID=:bundle_ID AND server=:server_bundle);"),bundle_ID=bundle_ID,server_bundle=server_bundle).scalar():
  return redirect("/")
 if g.conn.execute(text("SELECT NOT EXISTS(SELECT*FROM Items WHERE bundle_ID=:server_bundle AND name=:item_name);"),server_bundle=server_bundle,item_name=item_name).scalar():
  return redirect("/")
 if g.conn.execute(text("SELECT EXISTS(SELECT*FROM Bundles WHERE ID=:bundle_ID AND accepted);"),bundle_ID=bundle_ID).scalar():
  return redirect("/exchanged/"+username+"/"+password)
 return render_template("offered_item_1.html",username=username,password=password,bundle_ID=bundle_ID,server_bundle=server_bundle,item_name=item_name,**dict(g.conn.execute(text("SELECT description FROM Items WHERE bundle_ID=:server_bundle AND name=:item_name;"),server_bundle=server_bundle,item_name=item_name).first().items()+g.conn.execute(text("SELECT name,lister FROM Bundles WHERE ID=:server_bundle;"),server_bundle=server_bundle).first().items()))

@app.route("/offered_belongs_to_1/<username>/<password>/<bundle_ID>/<server_bundle>/<item_name>")
def offered_belongs_to_1(username,password,bundle_ID,server_bundle,item_name):
 if invalid(username,password):
  return redirect("/")
 if g.conn.execute(text("SELECT NOT EXISTS(SELECT*FROM Bundles WHERE lister=:username AND ID=:bundle_ID);"),username=username,bundle_ID=bundle_ID).scalar():
  return redirect("/")
 if g.conn.execute(text("SELECT EXISTS(SELECT*FROM Bundles WHERE ID=:bundle_ID AND server IS NULL);"),bundle_ID=bundle_ID).scalar():
  return redirect("/private/"+username+"/"+password)
 if g.conn.execute(text("SELECT NOT EXISTS(SELECT*FROM Bundles WHERE ID=:bundle_ID AND server=:server_bundle);"),bundle_ID=bundle_ID,server_bundle=server_bundle).scalar():
  return redirect("/")
 if g.conn.execute(text("SELECT NOT EXISTS(SELECT*FROM Items WHERE bundle_ID=:server_bundle AND name=:item_name);"),server_bundle=server_bundle,item_name=item_name).scalar():
  return redirect("/")
 if g.conn.execute(text("SELECT EXISTS(SELECT*FROM Bundles WHERE ID=:bundle_ID AND accepted);"),bundle_ID=bundle_ID).scalar():
  return redirect("/exchanged/"+username+"/"+password)
 categories=[]
 for category in g.conn.execute(text("SELECT category_name FROM Belongs_to WHERE bundle_ID=:server_bundle AND item_name=:item_name;"),server_bundle=server_bundle,item_name=item_name):
  categories.append(category["category_name"])
 return render_template("offered_belongs_to_1.html",username=username,password=password,bundle_ID=bundle_ID,server_bundle=server_bundle,item_name=item_name,categories=categories,**g.conn.execute(text("SELECT name,lister FROM Bundles WHERE ID=:server_bundle;"),server_bundle=server_bundle).first())

@app.route("/exchanged/<username>/<password>")
def exchanged(username,password):
 if invalid(username,password):
  return redirect("/")
 exchanges=[]
 for exchange in g.conn.execute(text("""
SELECT*FROM(
 SELECT tmp1.lister,tmp0.unseen,'server'bundle_type_0,'client'bundle_type_1,tmp1.stamp,tmp0.ID ID_0,tmp0.name name_0,tmp1.ID ID_1,tmp1.name name_1 FROM Bundles tmp0,Bundles tmp1 WHERE tmp0.lister=:username AND tmp0.listening AND tmp1.server=tmp0.ID AND tmp1.accepted
 UNION
 SELECT tmp1.lister,tmp0.unseen,'client'bundle_type_0,'server'bundle_type_1,tmp0.stamp,tmp0.ID ID_0,tmp0.name name_0,tmp1.ID ID_1,tmp1.name name_1 FROM Bundles tmp0,Bundles tmp1 WHERE tmp0.lister=:username AND tmp0.server=tmp1.ID AND tmp0.accepted)tmp0 ORDER BY stamp DESC"""),username=username):
  exchanges.append(exchange)
 g.conn.execute(text("""
UPDATE Bundles tmp0 SET unseen=FALSE WHERE tmp0.lister=:username AND tmp0.accepted OR EXISTS(
 SELECT*FROM Bundles tmp1 WHERE tmp1.server=tmp0.ID AND tmp1.accepted);"""),username=username)
 return render_template("exchanged.html",username=username,password=password,exchanges=exchanges)

def invalid_client_bundle_0(username,password,bundle_ID):
 return invalid(username,password)or g.conn.execute(text("SELECT NOT EXISTS(SELECT*FROM Bundles tmp0 WHERE tmp0.lister=:username AND tmp0.ID=:bundle_ID AND tmp0.accepted);"),username=username,bundle_ID=bundle_ID).scalar()

@app.route("/exchanged_client_bundle_0/<username>/<password>/<bundle_ID>")
def exchanged_client_bundle_0(username,password,bundle_ID):
 if invalid_client_bundle_0(username,password,bundle_ID):
  return redirect("/")
 return render_template("exchanged_client_bundle_0.html",username=username,password=password,bundle_ID=bundle_ID,**g.conn.execute(text("SELECT name,rating,comment FROM Bundles WHERE ID=:bundle_ID"),bundle_ID=bundle_ID).first())

def invalid_client_bundle_1(username,password,bundle_ID):
 return invalid(username,password)or g.conn.execute(text("""
SELECT NOT EXISTS(
 SELECT*FROM Bundles tmp0 WHERE tmp0.lister=:username AND EXISTS(
  SELECT*FROM Bundles tmp1 WHERE tmp1.ID=:bundle_ID AND tmp1.server=tmp0.ID AND tmp1.accepted));"""),username=username,bundle_ID=bundle_ID).scalar()

@app.route("/exchanged_client_bundle_1/<username>/<password>/<bundle_ID>")
def exchanged_client_bundle_1(username,password,bundle_ID):
 if invalid_client_bundle_1(username,password,bundle_ID):
  return redirect("/")
 return render_template("exchanged_client_bundle_1.html",username=username,password=password,bundle_ID=bundle_ID,**g.conn.execute(text("SELECT name,lister,rating,comment FROM Bundles WHERE ID=:bundle_ID"),bundle_ID=bundle_ID).first())

@app.route("/rate_client_bundle_1/<username>/<password>/<bundle_ID>/<rating>")
def rate_client_bundle_1(username,password,bundle_ID,rating):
 if invalid_client_bundle_1(username,password,bundle_ID):
  return redirect("/")
 if not rating.isdigit():
  return redirect("/")
 rating=int(rating)
 if rating<1or rating>5:
  return redirect("/")
 g.conn.execute(text("UPDATE Bundles SET rating=:rating WHERE ID=:bundle_ID;"),bundle_ID=bundle_ID,rating=rating)
 return redirect("/exchanged_client_bundle_1/"+username+"/"+password+"/"+bundle_ID)

@app.route("/comment_client_bundle_1/<username>/<password>/<bundle_ID>")
def comment_client_bundle_1(username,password,bundle_ID):
 if invalid_client_bundle_1(username,password,bundle_ID):
  return redirect("/")
 comment=request.args.get("comment")
 g.conn.execute(text("UPDATE Bundles SET comment=:comment WHERE ID=:bundle_ID;"),bundle_ID=bundle_ID,comment=comment)
 return redirect("/exchanged_client_bundle_1/"+username+"/"+password+"/"+bundle_ID)

def invalid_server_bundle_0(username,password,bundle_ID):
 return invalid(username,password)or g.conn.execute(text("""
SELECT NOT EXISTS(
 SELECT*FROM Bundles tmp0 WHERE tmp0.lister=:username AND tmp0.ID=:bundle_ID AND EXISTS(
  SELECT*FROM Bundles tmp1 WHERE tmp1.server=tmp0.ID AND tmp1.accepted));"""),username=username,bundle_ID=bundle_ID).scalar()

@app.route("/exchanged_server_bundle_0/<username>/<password>/<bundle_ID>")
def exchanged_server_bundle_0(username,password,bundle_ID):
 if invalid_server_bundle_0(username,password,bundle_ID):
  return redirect("/")
 return render_template("exchanged_server_bundle_0.html",username=username,password=password,bundle_ID=bundle_ID,**g.conn.execute(text("SELECT name,rating,comment,instructions FROM Bundles WHERE ID=:bundle_ID"),bundle_ID=bundle_ID).first())

def invalid_server_bundle_1(username,password,bundle_ID):
 return invalid(username,password)or g.conn.execute(text("SELECT NOT EXISTS(SELECT*FROM Bundles tmp0 WHERE tmp0.lister=:username AND tmp0.server=:bundle_ID AND tmp0.accepted);"),username=username,bundle_ID=bundle_ID).scalar()

@app.route("/exchanged_server_bundle_1/<username>/<password>/<bundle_ID>")
def exchanged_server_bundle_1(username,password,bundle_ID):
 if invalid_server_bundle_1(username,password,bundle_ID):
  return redirect("/")
 return render_template("exchanged_server_bundle_1.html",username=username,password=password,bundle_ID=bundle_ID,**g.conn.execute(text("SELECT name,lister,rating,comment,instructions FROM Bundles WHERE ID=:bundle_ID"),bundle_ID=bundle_ID).first())

@app.route("/rate_server_bundle_1/<username>/<password>/<bundle_ID>/<rating>")
def rate_server_bundle_1(username,password,bundle_ID,rating):
 if invalid_server_bundle_1(username,password,bundle_ID):
  return redirect("/")
 if not rating.isdigit():
  return redirect("/")
 rating=int(rating)
 if rating<1or rating>5:
  return redirect("/")
 g.conn.execute(text("UPDATE Bundles SET rating=:rating WHERE ID=:bundle_ID;"),bundle_ID=bundle_ID,rating=rating)
 return redirect("/exchanged_server_bundle_1/"+username+"/"+password+"/"+bundle_ID)

@app.route("/comment_server_bundle_1/<username>/<password>/<bundle_ID>")
def comment_server_bundle_1(username,password,bundle_ID):
 if invalid_server_bundle_1(username,password,bundle_ID):
  return redirect("/")
 comment=request.args.get("comment")
 g.conn.execute(text("UPDATE Bundles SET comment=:comment WHERE ID=:bundle_ID;"),bundle_ID=bundle_ID,comment=comment)
 return redirect("/exchanged_server_bundle_1/"+username+"/"+password+"/"+bundle_ID)

@app.route("/client_history/<username>/<password>/<bundle_ID>/<client>")
def client_history(username,password,bundle_ID,client):
 if invalid_public(username,password,bundle_ID):
  return redirect("/")
 reviews=[]
 for review in g.conn.execute(text("""
SELECT*FROM(
 SELECT tmp1.stamp,tmp0.rating,tmp0.comment,tmp1.lister,(
  SELECT AVG(tmp2.rating)FROM Bundles tmp2 WHERE tmp2.lister=tmp1.lister)average_rating,(
  SELECT COUNT(*)FROM Bundles tmp2 WHERE tmp2.lister=tmp1.lister AND tmp2.rating IS NOT NULL)rating_count FROM Bundles tmp0,Bundles tmp1 WHERE tmp0.lister=:client AND tmp0.rating IS NOT NULL AND tmp1.server=tmp0.ID
 UNION
 SELECT tmp0.stamp,tmp0.rating,tmp0.comment,tmp1.lister,(
  SELECT AVG(tmp2.rating)FROM Bundles tmp2 WHERE tmp2.lister=tmp1.lister)average_rating,(
  SELECT COUNT(*)FROM Bundles tmp2 WHERE tmp2.lister=tmp1.lister AND tmp2.rating IS NOT NULL)rating_count FROM Bundles tmp0,Bundles tmp1 WHERE tmp0.lister=:client AND tmp0.rating IS NOT NULL AND tmp0.server=tmp1.ID)tmp0 ORDER BY tmp0.stamp DESC;"""),client=client):
  reviews.append({"stamp":review["stamp"],"rating":review["rating"],"comment":review["comment"],"lister":review["lister"],"average_rating":float(str(review["average_rating"]))if review["average_rating"]else None,"rating_count":review["rating_count"]})
 return render_template("client_history.html",username=username,password=password,bundle_ID=bundle_ID,client=client,reviews=reviews)

@app.route("/server_history/<username>/<password>/<bundle_ID>/<server>")
def server_history(username,password,bundle_ID,server):
 if invalid_private(username,password,bundle_ID):
  return redirect("/")
 reviews=[]
 for review in g.conn.execute(text("""
SELECT*FROM(
 SELECT tmp1.stamp,tmp0.rating,tmp0.comment,tmp1.lister,(
  SELECT AVG(tmp2.rating)FROM Bundles tmp2 WHERE tmp2.lister=tmp1.lister)average_rating,(
  SELECT COUNT(*)FROM Bundles tmp2 WHERE tmp2.lister=tmp1.lister AND tmp2.rating IS NOT NULL)rating_count FROM Bundles tmp0,Bundles tmp1 WHERE tmp0.lister=:server AND tmp0.rating IS NOT NULL AND tmp1.server=tmp0.ID
 UNION
 SELECT tmp0.stamp,tmp0.rating,tmp0.comment,tmp1.lister,(
  SELECT AVG(tmp2.rating)FROM Bundles tmp2 WHERE tmp2.lister=tmp1.lister)average_rating,(
  SELECT COUNT(*)FROM Bundles tmp2 WHERE tmp2.lister=tmp1.lister AND tmp2.rating IS NOT NULL)rating_count FROM Bundles tmp0,Bundles tmp1 WHERE tmp0.lister=:server AND tmp0.rating IS NOT NULL AND tmp0.server=tmp1.ID)tmp0 ORDER BY tmp0.stamp DESC;"""),server=server):
  reviews.append({"stamp":review["stamp"],"rating":review["rating"],"comment":review["comment"],"lister":review["lister"],"average_rating":float(str(review["average_rating"]))if review["average_rating"]else None,"rating_count":review["rating_count"]})
 return render_template("server_history.html",username=username,password=password,bundle_ID=bundle_ID,server=server,reviews=reviews)

@app.route("/exchanged_client_items_0/<username>/<password>/<bundle_ID>")
def exchanged_client_items_0(username,password,bundle_ID):
 if invalid_client_bundle_0(username,password,bundle_ID):
  return redirect("/")
 items=[]
 for item in g.conn.execute(text("SELECT name FROM Items WHERE bundle_ID=:bundle_ID;"),bundle_ID=bundle_ID):
  items.append(item["name"])
 return render_template("exchanged_client_items_0.html",username=username,password=password,bundle_ID=bundle_ID,items=items,**g.conn.execute(text("SELECT name FROM Bundles WHERE ID=:bundle_ID;"),bundle_ID=bundle_ID).first())

def invalid_client_item_0(username,password,bundle_ID,item_name):
 return invalid_client_bundle_0(username,password,bundle_ID)or g.conn.execute(text("SELECT NOT EXISTS(SELECT*FROM Items WHERE bundle_ID=:bundle_ID AND name=:item_name);"),bundle_ID=bundle_ID,item_name=item_name).scalar()

@app.route("/exchanged_client_item_0/<username>/<password>/<bundle_ID>/<item_name>")
def exchanged_client_item_0(username,password,bundle_ID,item_name):
 if invalid_client_item_0(username,password,bundle_ID,item_name):
  return redirect("/")
 return render_template("exchanged_client_item_0.html",username=username,password=password,bundle_ID=bundle_ID,item_name=item_name,**dict(g.conn.execute(text("SELECT description FROM Items WHERE bundle_ID=:bundle_ID AND name=:item_name;"),bundle_ID=bundle_ID,item_name=item_name).first().items()+g.conn.execute(text("SELECT name FROM Bundles WHERE ID=:bundle_ID;"),bundle_ID=bundle_ID).first().items()))

@app.route("/exchanged_client_belongs_to_0/<username>/<password>/<bundle_ID>/<item_name>")
def exchanged_client_belongs_to_0(username,password,bundle_ID,item_name):
 if invalid_client_item_0(username,password,bundle_ID,item_name):
  return redirect("/")
 categories=[]
 for category in g.conn.execute(text("SELECT category_name FROM Belongs_to WHERE bundle_ID=:bundle_ID AND item_name=:item_name;"),bundle_ID=bundle_ID,item_name=item_name):
  categories.append(category["category_name"])
 return render_template("exchanged_client_belongs_to_0.html",username=username,password=password,bundle_ID=bundle_ID,item_name=item_name,categories=categories,**g.conn.execute(text("SELECT name FROM Bundles WHERE ID=:bundle_ID;"),bundle_ID=bundle_ID).first())

@app.route("/exchanged_client_items_1/<username>/<password>/<bundle_ID>")
def exchanged_client_items_1(username,password,bundle_ID):
 if invalid_client_bundle_1(username,password,bundle_ID):
  return redirect("/")
 items=[]
 for item in g.conn.execute(text("SELECT name FROM Items WHERE bundle_ID=:bundle_ID;"),bundle_ID=bundle_ID):
  items.append(item["name"])
 return render_template("exchanged_client_items_1.html",username=username,password=password,bundle_ID=bundle_ID,items=items,**g.conn.execute(text("SELECT name,lister FROM Bundles WHERE ID=:bundle_ID;"),bundle_ID=bundle_ID).first())

def invalid_client_item_1(username,password,bundle_ID,item_name):
 return invalid_client_bundle_1(username,password,bundle_ID)or g.conn.execute(text("SELECT NOT EXISTS(SELECT*FROM Items WHERE bundle_ID=:bundle_ID AND name=:item_name);"),bundle_ID=bundle_ID,item_name=item_name).scalar()

@app.route("/exchanged_client_item_1/<username>/<password>/<bundle_ID>/<item_name>")
def exchanged_client_item_1(username,password,bundle_ID,item_name):
 if invalid_client_item_1(username,password,bundle_ID,item_name):
  return redirect("/")
 return render_template("exchanged_client_item_1.html",username=username,password=password,bundle_ID=bundle_ID,item_name=item_name,**dict(g.conn.execute(text("SELECT description FROM Items WHERE bundle_ID=:bundle_ID AND name=:item_name;"),bundle_ID=bundle_ID,item_name=item_name).first().items()+g.conn.execute(text("SELECT name,lister FROM Bundles WHERE ID=:bundle_ID;"),bundle_ID=bundle_ID).first().items()))

@app.route("/exchanged_client_belongs_to_1/<username>/<password>/<bundle_ID>/<item_name>")
def exchanged_client_belongs_to_1(username,password,bundle_ID,item_name):
 if invalid_client_item_1(username,password,bundle_ID,item_name):
  return redirect("/")
 categories=[]
 for category in g.conn.execute(text("SELECT category_name FROM Belongs_to WHERE bundle_ID=:bundle_ID AND item_name=:item_name;"),bundle_ID=bundle_ID,item_name=item_name):
  categories.append(category["category_name"])
 return render_template("exchanged_client_belongs_to_1.html",username=username,password=password,bundle_ID=bundle_ID,item_name=item_name,categories=categories,**g.conn.execute(text("SELECT name,lister FROM Bundles WHERE ID=:bundle_ID;"),bundle_ID=bundle_ID).first())

@app.route("/exchanged_server_items_0/<username>/<password>/<bundle_ID>")
def exchanged_server_items_0(username,password,bundle_ID):
 if invalid_server_bundle_0(username,password,bundle_ID):
  return redirect("/")
 items=[]
 for item in g.conn.execute(text("SELECT name FROM Items WHERE bundle_ID=:bundle_ID;"),bundle_ID=bundle_ID):
  items.append(item["name"])
 return render_template("exchanged_server_items_0.html",username=username,password=password,bundle_ID=bundle_ID,items=items,**g.conn.execute(text("SELECT name FROM Bundles WHERE ID=:bundle_ID;"),bundle_ID=bundle_ID).first())

def invalid_server_item_0(username,password,bundle_ID,item_name):
 return invalid_server_bundle_0(username,password,bundle_ID)or g.conn.execute(text("SELECT NOT EXISTS(SELECT*FROM Items WHERE bundle_ID=:bundle_ID AND name=:item_name);"),bundle_ID=bundle_ID,item_name=item_name).scalar()

@app.route("/exchanged_server_item_0/<username>/<password>/<bundle_ID>/<item_name>")
def exchanged_server_item_0(username,password,bundle_ID,item_name):
 if invalid_server_item_0(username,password,bundle_ID,item_name):
  return redirect("/")
 return render_template("exchanged_server_item_0.html",username=username,password=password,bundle_ID=bundle_ID,item_name=item_name,**dict(g.conn.execute(text("SELECT description FROM Items WHERE bundle_ID=:bundle_ID AND name=:item_name;"),bundle_ID=bundle_ID,item_name=item_name).first().items()+g.conn.execute(text("SELECT name FROM Bundles WHERE ID=:bundle_ID;"),bundle_ID=bundle_ID).first().items()))

@app.route("/exchanged_server_belongs_to_0/<username>/<password>/<bundle_ID>/<item_name>")
def exchanged_server_belongs_to_0(username,password,bundle_ID,item_name):
 if invalid_server_item_0(username,password,bundle_ID,item_name):
  return redirect("/")
 categories=[]
 for category in g.conn.execute(text("SELECT category_name FROM Belongs_to WHERE bundle_ID=:bundle_ID AND item_name=:item_name;"),bundle_ID=bundle_ID,item_name=item_name):
  categories.append(category["category_name"])
 return render_template("exchanged_server_belongs_to_0.html",username=username,password=password,bundle_ID=bundle_ID,item_name=item_name,categories=categories,**g.conn.execute(text("SELECT name FROM Bundles WHERE ID=:bundle_ID;"),bundle_ID=bundle_ID).first())

@app.route("/exchanged_server_items_1/<username>/<password>/<bundle_ID>")
def exchanged_server_items_1(username,password,bundle_ID):
 if invalid_server_bundle_1(username,password,bundle_ID):
  return redirect("/")
 items=[]
 for item in g.conn.execute(text("SELECT name FROM Items WHERE bundle_ID=:bundle_ID;"),bundle_ID=bundle_ID):
  items.append(item["name"])
 return render_template("exchanged_server_items_1.html",username=username,password=password,bundle_ID=bundle_ID,items=items,**g.conn.execute(text("SELECT name,lister FROM Bundles WHERE ID=:bundle_ID;"),bundle_ID=bundle_ID).first())

def invalid_server_item_1(username,password,bundle_ID,item_name):
 return invalid_server_bundle_1(username,password,bundle_ID)or g.conn.execute(text("SELECT NOT EXISTS(SELECT*FROM Items WHERE bundle_ID=:bundle_ID AND name=:item_name);"),bundle_ID=bundle_ID,item_name=item_name).scalar()

@app.route("/exchanged_server_item_1/<username>/<password>/<bundle_ID>/<item_name>")
def exchanged_server_item_1(username,password,bundle_ID,item_name):
 if invalid_server_item_1(username,password,bundle_ID,item_name):
  return redirect("/")
 return render_template("exchanged_server_item_1.html",username=username,password=password,bundle_ID=bundle_ID,item_name=item_name,**dict(g.conn.execute(text("SELECT description FROM Items WHERE bundle_ID=:bundle_ID AND name=:item_name;"),bundle_ID=bundle_ID,item_name=item_name).first().items()+g.conn.execute(text("SELECT name,lister FROM Bundles WHERE ID=:bundle_ID;"),bundle_ID=bundle_ID).first().items()))

@app.route("/exchanged_server_belongs_to_1/<username>/<password>/<bundle_ID>/<item_name>")
def exchanged_server_belongs_to_1(username,password,bundle_ID,item_name):
 if invalid_server_item_1(username,password,bundle_ID,item_name):
  return redirect("/")
 categories=[]
 for category in g.conn.execute(text("SELECT category_name FROM Belongs_to WHERE bundle_ID=:bundle_ID AND item_name=:item_name;"),bundle_ID=bundle_ID,item_name=item_name):
  categories.append(category["category_name"])
 return render_template("exchanged_server_belongs_to_1.html",username=username,password=password,bundle_ID=bundle_ID,item_name=item_name,categories=categories,**g.conn.execute(text("SELECT name,lister FROM Bundles WHERE ID=:bundle_ID;"),bundle_ID=bundle_ID).first())

@app.route("/public_items/<username>/<password>/<bundle_ID>")
def public_items(username,password,bundle_ID):
 if invalid_public(username,password,bundle_ID):
  return redirect("/")
 items=[]
 for item in g.conn.execute(text("SELECT name FROM Items WHERE bundle_ID=:bundle_ID;"),bundle_ID=bundle_ID):
  items.append(item["name"])
 return render_template("public_items.html",username=username,password=password,bundle_ID=bundle_ID,items=items,**g.conn.execute(text("SELECT name FROM Bundles WHERE ID=:bundle_ID;"),bundle_ID=bundle_ID).first())

def invalid_public_item(username,password,bundle_ID,item_name):
 return invalid_public(username,password,bundle_ID)or g.conn.execute(text("SELECT NOT EXISTS(SELECT*FROM Items WHERE bundle_ID=:bundle_ID AND name=:item_name);"),bundle_ID=bundle_ID,item_name=item_name).scalar()

@app.route("/public_item/<username>/<password>/<bundle_ID>/<item_name>")
def public_item(username,password,bundle_ID,item_name):
 if invalid_public_item(username,password,bundle_ID,item_name):
  return redirect("/")
 return render_template("public_item.html",username=username,password=password,bundle_ID=bundle_ID,item_name=item_name,**dict(g.conn.execute(text("SELECT description FROM Items WHERE bundle_ID=:bundle_ID AND name=:item_name;"),bundle_ID=bundle_ID,item_name=item_name).first().items()+g.conn.execute(text("SELECT name FROM Bundles WHERE ID=:bundle_ID;"),bundle_ID=bundle_ID).first().items()))

@app.route("/public_belongs_to/<username>/<password>/<bundle_ID>/<item_name>")
def public_belongs_to(username,password,bundle_ID,item_name):
 if invalid_public_item(username,password,bundle_ID,item_name):
  return redirect("/")
 categories=[]
 for category in g.conn.execute(text("SELECT category_name FROM Belongs_to WHERE bundle_ID=:bundle_ID AND item_name=:item_name;"),bundle_ID=bundle_ID,item_name=item_name):
  categories.append(category["category_name"])
 return render_template("public_belongs_to.html",username=username,password=password,bundle_ID=bundle_ID,item_name=item_name,categories=categories,**g.conn.execute(text("SELECT name FROM Bundles WHERE ID=:bundle_ID;"),bundle_ID=bundle_ID).first())

@app.route("/client_items/<username>/<password>/<bundle_ID>/<client>/<client_bundle>")
def client_items(username,password,bundle_ID,client,client_bundle):
 if invalid_public(username,password,bundle_ID):
  return redirect("/")
 if g.conn.execute(text("SELECT NOT EXISTS(SELECT*FROM Bundles WHERE lister=:client AND ID=:client_bundle AND server=:bundle_ID);"),bundle_ID=bundle_ID,client=client,client_bundle=client_bundle).scalar():
  return render_template("client_bundle_unavailable.html",username=username,password=password,bundle_ID=bundle_ID,client=client)
 items=[]
 for item in g.conn.execute(text("SELECT name FROM Items WHERE bundle_ID=:client_bundle;"),client_bundle=client_bundle):
  items.append(item["name"])
 return render_template("client_items.html",username=username,password=password,bundle_ID=bundle_ID,client=client,client_bundle=client_bundle,items=items,**g.conn.execute(text("SELECT name FROM Bundles WHERE ID=:client_bundle;"),client_bundle=client_bundle).first())

@app.route("/client_item/<username>/<password>/<bundle_ID>/<client>/<client_bundle>/<item_name>")
def client_item(username,password,bundle_ID,client,client_bundle,item_name):
 if invalid_public(username,password,bundle_ID):
  return redirect("/")
 if g.conn.execute(text("SELECT NOT EXISTS(SELECT*FROM Bundles WHERE lister=:client AND ID=:client_bundle AND server=:bundle_ID);"),bundle_ID=bundle_ID,client=client,client_bundle=client_bundle).scalar():
  return render_template("client_bundle_unavailable.html",username=username,password=password,bundle_ID=bundle_ID,client=client)
 if g.conn.execute(text("SELECT NOT EXISTS(SELECT*FROM Items WHERE bundle_ID=:client_bundle AND name=:item_name);"),client_bundle=client_bundle,item_name=item_name).scalar():
  return redirect("/")
 return render_template("client_item.html",username=username,password=password,bundle_ID=bundle_ID,client=client,client_bundle=client_bundle,item_name=item_name,**dict(g.conn.execute(text("SELECT description FROM Items WHERE bundle_ID=:client_bundle AND name=:item_name;"),client_bundle=client_bundle,item_name=item_name).first().items()+g.conn.execute(text("SELECT name FROM Bundles WHERE ID=:client_bundle;"),client_bundle=client_bundle).first().items()))

@app.route("/client_belongs_to/<username>/<password>/<bundle_ID>/<client>/<client_bundle>/<item_name>")
def client_belongs_to(username,password,bundle_ID,client,client_bundle,item_name):
 if invalid_public(username,password,bundle_ID):
  return redirect("/")
 if g.conn.execute(text("SELECT NOT EXISTS(SELECT*FROM Bundles WHERE lister=:client AND ID=:client_bundle AND server=:bundle_ID);"),bundle_ID=bundle_ID,client=client,client_bundle=client_bundle).scalar():
  return render_template("client_bundle_unavailable.html",username=username,password=password,bundle_ID=bundle_ID,client=client)
 if g.conn.execute(text("SELECT NOT EXISTS(SELECT*FROM Items WHERE bundle_ID=:client_bundle AND name=:item_name);"),client_bundle=client_bundle,item_name=item_name).scalar():
  return redirect("/")
 categories=[]
 for category in g.conn.execute(text("SELECT category_name FROM Belongs_to WHERE bundle_ID=:client_bundle AND item_name=:item_name;"),client_bundle=client_bundle,item_name=item_name):
  categories.append(category["category_name"])
 return render_template("client_belongs_to.html",username=username,password=password,bundle_ID=bundle_ID,client=client,client_bundle=client_bundle,item_name=item_name,categories=categories,**g.conn.execute(text("SELECT name FROM Bundles WHERE ID=:client_bundle;"),client_bundle=client_bundle).first())

@app.route("/server_items/<username>/<password>/<bundle_ID>/<server>/<server_bundle>")
def server_items(username,password,bundle_ID,server,server_bundle):
 if invalid_private(username,password,bundle_ID):
  return redirect("/")
 if g.conn.execute(text("""
SELECT NOT EXISTS(
 SELECT*FROM Bundles tmp0 WHERE tmp0.ID=:server_bundle AND tmp0.listening AND NOT EXISTS(
  SELECT*FROM Bundles tmp1 WHERE tmp1.server=:server_bundle AND tmp1.accepted));"""),server=server,server_bundle=server_bundle).scalar():
  return render_template("server_bundle_unavailable.html",username=username,password=password,bundle_ID=bundle_ID,server=server)
 items=[]
 for item in g.conn.execute(text("SELECT name FROM Items WHERE bundle_ID=:server_bundle;"),server_bundle=server_bundle):
  items.append(item["name"])
 return render_template("server_items.html",username=username,password=password,bundle_ID=bundle_ID,server=server,server_bundle=server_bundle,items=items,**g.conn.execute(text("SELECT name FROM Bundles WHERE ID=:server_bundle;"),server_bundle=server_bundle).first())

@app.route("/server_item/<username>/<password>/<bundle_ID>/<server>/<server_bundle>/<item_name>")
def server_item(username,password,bundle_ID,server,server_bundle,item_name):
 if invalid_private(username,password,bundle_ID):
  return redirect("/")
 if g.conn.execute(text("""
SELECT NOT EXISTS(
 SELECT*FROM Bundles tmp0 WHERE tmp0.ID=:server_bundle AND tmp0.listening AND NOT EXISTS(
  SELECT*FROM Bundles tmp1 WHERE tmp1.server=:server_bundle AND tmp1.accepted));"""),server=server,server_bundle=server_bundle).scalar():
  return render_template("server_bundle_unavailable.html",username=username,password=password,bundle_ID=bundle_ID,server=server)
 if g.conn.execute(text("SELECT NOT EXISTS(SELECT*FROM Items WHERE bundle_ID=:server_bundle AND name=:item_name);"),server_bundle=server_bundle,item_name=item_name).scalar():
  return redirect("/")
 return render_template("server_item.html",username=username,password=password,bundle_ID=bundle_ID,server=server,server_bundle=server_bundle,item_name=item_name,**dict(g.conn.execute(text("SELECT description FROM Items WHERE bundle_ID=:server_bundle AND name=:item_name;"),server_bundle=server_bundle,item_name=item_name).first().items()+g.conn.execute(text("SELECT name FROM Bundles WHERE ID=:server_bundle;"),server_bundle=server_bundle).first().items()))

@app.route("/server_belongs_to/<username>/<password>/<bundle_ID>/<server>/<server_bundle>/<item_name>")
def server_belongs_to(username,password,bundle_ID,server,server_bundle,item_name):
 if invalid_private(username,password,bundle_ID):
  return redirect("/")
 if g.conn.execute(text("""
SELECT NOT EXISTS(
 SELECT*FROM Bundles tmp0 WHERE tmp0.ID=:server_bundle AND tmp0.listening AND NOT EXISTS(
  SELECT*FROM Bundles tmp1 WHERE tmp1.server=:server_bundle AND tmp1.accepted));"""),server=server,server_bundle=server_bundle).scalar():
  return render_template("server_bundle_unavailable.html",username=username,password=password,bundle_ID=bundle_ID,server=server)
 if g.conn.execute(text("SELECT NOT EXISTS(SELECT*FROM Items WHERE bundle_ID=:server_bundle AND name=:item_name);"),server_bundle=server_bundle,item_name=item_name).scalar():
  return redirect("/")
 categories=[]
 for category in g.conn.execute(text("SELECT category_name FROM Belongs_to WHERE bundle_ID=:server_bundle AND item_name=:item_name;"),server_bundle=server_bundle,item_name=item_name):
  categories.append(category["category_name"])
 return render_template("server_belongs_to.html",username=username,password=password,bundle_ID=bundle_ID,server=server,server_bundle=server_bundle,item_name=item_name,categories=categories,**g.conn.execute(text("SELECT name FROM Bundles WHERE ID=:server_bundle;"),server_bundle=server_bundle).first())

if __name__ == "__main__":
  import click

  @click.command()
  @click.option('--debug', is_flag=True)
  @click.option('--threaded', is_flag=True)
  @click.argument('HOST', default='0.0.0.0')
  @click.argument('PORT', default=8111, type=int)
  def run(debug, threaded, host, port):
    HOST, PORT = host, port
    print "running on %s:%d" % (HOST, PORT)
    app.run(host=HOST, port=PORT, debug=debug, threaded=threaded)

  run()
