from flask import Flask, request
from flask_cors import CORS, cross_origin
from flask_api import status
from os import listdir, getcwd
from csv import *
import pandas as pd
import json

app = Flask(__name__)
CORS(app)
app.config["CORS_HEADERS"] = "Content-Type"

# TODO: refactor this to use Flask-limiter (pip install that) and dynamo

@app.route("/")
def index():
    # TODO this should probably return something more substantial (a full html? can you do that?)
    # that just explains the endpoints available (just 1) and the args you can pass / it expects
    return "<p>Welcome! This API is currently a work in progress.</p>"

# the main one
@app.route("/data", methods=['GET'])
@cross_origin()
def data():
    # get the data
    # TODO maybe this can be moved top-level ? to prevent loading this in each time we call
    csv_files = [f for f in listdir(getcwd()) if f.endswith(".csv")]

    if not len(csv_files) > 0:
        return "Data store not found", status.HTTP_400_BAD_REQUEST

    print("Found and using CSV file " + csv_files[0] + " as data store.")
    file_store = csv_files[0]

    all_data = pd.read_csv(file_store)
    # print(all_data)

    # process params from query args
    # if not present, have some defaults
    solved_only = True
    difficulty = "expert"
    # minimums
    board_3bv_threshold = 0
    solved_percent_threshold = 0
    effiency_threshold = 0

    query_solved_only = request.args.get("solved")
    query_difficulty = request.args.get("difficulty")
    query_board_3bv_threshold = request.args.get("3bv_threshold")
    query_solved_percent_threshold = request.args.get("solved_percent_threshold")
    query_efficiency_threshold = request.args.get("efficiency_threshold")
    # TODO: 3bvps threshold ?

    if query_solved_only is not None:
        if query_solved_only.lower() not in ["true", "false"]:
            print (query_solved_only.lower())
            return "Invalid filter", status.HTTP_400_BAD_REQUEST
        solved_only = query_solved_only.lower() == "true"

    if query_difficulty is not None:
        if query_difficulty.lower() not in ["beginner", "intermediate", "expert"]:
            return "Invalid filter", status.HTTP_400_BAD_REQUEST
        difficulty = query_difficulty.lower()

    if query_board_3bv_threshold is not None:
        # TODO input range validation (positive number)
        try:
            board_3bv_threshold = float(query_board_3bv_threshold)
        except:
            return "Invalid filter", status.HTTP_400_BAD_REQUEST
        
    if query_efficiency_threshold is not None:
        try:
            effiency_threshold = float(query_efficiency_threshold)
        except:
            return "Invalid filter", status.HTTP_400_BAD_REQUEST
        
    if query_solved_percent_threshold is not None:
        try:
            solved_percent_threshold = float(query_solved_percent_threshold)
        except:
            return "Invalid filter", status.HTTP_400_BAD_REQUEST

    # print(solved_only, difficulty, board_3bv_threshold, solved_percent_threshold, effiency_threshold)

    # Note: should probably just always exclude stuff with 0 efficiency / NaN 3bvp/s
    all_data["Difficulty"] = all_data["Difficulty"]
    all_data["Efficiency"] = all_data["Efficiency"].apply(lambda x: float(x))
    all_data["3BV"] = all_data["3BV"].apply(lambda x: int(x))
    all_data["Completed 3BV"] = all_data["Completed 3BV"].apply(lambda x: int(x))
    all_data["Completion"] = (all_data["Completed 3BV"] / all_data["3BV"]) * 100
    return_data = all_data
    
    if solved_only:
        return_data = all_data.loc[all_data["Board Solved"]] # == True
    
    return_data = return_data.loc[return_data["Difficulty"] == difficulty]
    return_data = return_data.loc[return_data["3BV"] >= board_3bv_threshold]
    return_data = return_data.loc[return_data["Efficiency"] >= effiency_threshold]

    if not solved_only:
        return_data = return_data.loc[return_data["Completion"] >= float(solved_percent_threshold)]

    # print(return_data)

    response = json.loads(return_data.to_json(orient="records"))
    # print(json.dumps(response, indent=2))
    return response
