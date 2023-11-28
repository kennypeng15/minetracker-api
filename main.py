from flask import Flask, request
from flask_cors import CORS, cross_origin
import pandas as pd
import simplejson
from dotenv import load_dotenv
from os.path import join, dirname
import boto3
import os
from datetime import datetime, timedelta

app = Flask(__name__)

# enable cross-origin resource sharing
CORS(app)
app.config["CORS_HEADERS"] = "Content-Type"

# load necessary environment variables
dotenv_path = join(dirname(__file__), '.env')
load_dotenv(dotenv_path)

# connect to Dynamo
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ['DYNAMO_NAME'])

# naive cache for scanned db entries
all_db_data = []

# timer to keep track of last time a full scan of dynamo was made
# initialize to a datetime in the past so that, on first API request, full scan is always made
last_scan_time = datetime(2020, 1, 1)

# refresh threshold (in seconds): set it to 24 hours
refresh_hours = 24
refresh_threshold = 60 * 60 * refresh_hours

# provides information about the API itself - how to use, etc.
@app.route("/")
@cross_origin()
def index():
    return "<h1>Welcome to MineTracker!</h1> \
        <p>Please note that this API is still somewhat a work-in-progress.</p> \
        <p>The primary endpoint of interest here is /data, which is a GET endpoint returning data about minesweeper.online games.</p> \
        <p>The endpoint takes in some optional query parameters:</p>  \
        <ul> \
        <li>solved: values either [true, false], default true. indicates if you want to receive only data about solved games.</li> \
        <li>difficulty: values either [beginner, intermediate, expert], default expert. indicates which difficulty you want data about.</li> \
        <li>3bv_threshold: values any positive integer. defines the minimum board 3bv for games you want data about.</li> \
        <li>solved_percent_threshold: values any positive integer. defines the minimum solved percentage for games you want data about.</li> \
        <li>efficiency_threshold: values any positive integer. defines the minimum efficiency for games you want data about.</li> \
        </ul>"

# provides diagnostic information about the API
@app.route("/status")
@cross_origin()
def status():
    # use the globally declared cache and last scan value
    global all_db_data
    global last_scan_time
    global refresh_hours

    # determine how many items are in the cache, and how long until next refresh
    item_count = len(all_db_data)
    next_refresh_time = last_scan_time + timedelta(hours=refresh_hours)
    seconds_until_next_refresh = (next_refresh_time - datetime.now()).total_seconds()
    
    return f"<h1>MineTracker diagnostic information:</h1> \
        <p>Item count (cache): {item_count}</p> \
        <p>Last refresh time: {last_scan_time}</p> \
        <p>Next refresh time: {next_refresh_time}</p> \
        <p>Hours until next refresh: {seconds_until_next_refresh / 3600}</p>"

# the main one
@app.route("/data", methods=['GET'])
@cross_origin()
def data():
    # use the globally declared cache and last scan value
    global all_db_data
    global last_scan_time

    # if the time delta between now and the last_scan_time is more than refresh_threshold, 
    # initiate a full scan of the DB, and cache the results.
    # if not, used the cached data.
    if (datetime.now() - last_scan_time).total_seconds() > refresh_threshold:
        print("initializing full DB scan.")
        # initialize a full scan
        # clear the cache first
        all_db_data = []
        scan_kwargs = { "ReturnConsumedCapacity": "TOTAL" }
        done = False
        start_key = None
        while not done:
            if start_key:
                scan_kwargs["ExclusiveStartKey"] = start_key
            response = table.scan(**scan_kwargs)
            all_db_data.extend(response.get("Items", []))
            start_key = response.get("LastEvaluatedKey", None)
            done = start_key is None
            print("Scan consumed capacity: ")
            print(response.get("ConsumedCapacity", ""))
        last_scan_time = datetime.now()
    else:
        print("using cached DB data.")

    # convert the data to a pandas dataframe for ease of use and filtering
    all_data_df = pd.DataFrame(all_db_data)

    # create some default values for what's processed from the query arguments.
    solved_only = True
    difficulty = "expert"
    # minimums
    board_3bv_threshold = 0
    solved_percent_threshold = 50
    effiency_threshold = 0

    # actually process params from query args
    query_solved_only = request.args.get("solved")
    query_difficulty = request.args.get("difficulty")
    query_board_3bv_threshold = request.args.get("3bv_threshold")
    query_solved_percent_threshold = request.args.get("solved_percent_threshold")
    query_efficiency_threshold = request.args.get("efficiency_threshold")
    # TODO: 3bvps threshold ?

    # validate the query args
    if query_solved_only is not None:
        if query_solved_only.lower() not in ["true", "false"]:
            print (query_solved_only.lower())
            return "Invalid filter - solved only value not one of two valid selections (true, false)", 400
        solved_only = query_solved_only.lower() == "true"

    if query_difficulty is not None:
        if query_difficulty.lower() not in ["beginner", "intermediate", "expert"]:
            return "Invalid filter - difficulty value not one of three valid selections (beginner, intermediate, expert)", 400
        difficulty = query_difficulty.lower()

    if query_board_3bv_threshold is not None:
        # TODO input range validation (positive number)
        try:
            board_3bv_threshold = float(query_board_3bv_threshold)
        except:
            return "Invalid filter - board 3bv treshold not a valid number", 400
        
    if query_efficiency_threshold is not None:
        try:
            effiency_threshold = float(query_efficiency_threshold)
        except:
            return "Invalid filter - efficiency treshold not a valid number", 400
        
    if query_solved_percent_threshold is not None:
        try:
            solved_percent_threshold = float(query_solved_percent_threshold)
        except:
            return "Invalid filter - solved percent treshold not a valid number", 400
        # TODO: for this one in particular, the threshold needs to be greater or equal to 50

    # print(solved_only, difficulty, board_3bv_threshold, solved_percent_threshold, effiency_threshold)

    # build a return dataframe
    return_data = all_data_df
    if solved_only:
        return_data = all_data_df.loc[all_data_df["board-solved"]] # == True
    
    return_data = return_data.loc[return_data["difficulty"] == difficulty]
    return_data = return_data.loc[return_data["board-3bv"] >= board_3bv_threshold]
    return_data = return_data.loc[return_data["efficiency"] >= effiency_threshold]

    if not solved_only:
        return_data = return_data.loc[return_data["solve-percentage"] >= float(solved_percent_threshold)]

    response = return_data.to_json(orient="records")
    # print(response)
    return response