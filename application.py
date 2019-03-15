# Copyright 2019 by Quopt IT Services BV
#
#  Licensed under the Artistic License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#    https://opensource.org/licenses/Artistic-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.

from flask import Flask, jsonify, request, url_for, render_template
import datetime
import json
import time
import os
import hashlib, uuid
import types
import traceback
import shutil
from flask_cors import CORS
from flask_compress import Compress
from datetime import datetime, timezone, timedelta
from waitress import serve
import sys

# Change this line for a non standard REST API installation path
sys.path.insert(0, '.')
sys.path.insert(0, '../ITS rest api/')

import ITSRestAPILogin
import ITSMailer
import ITSRestAPIORMExtensions
import ITSRestAPIORM
import ITSRestAPIDB
import ITSRestAPISettings
import ITSJsonify
from ITSRestAPIORMExtendedFunctions import *
from ITSLogging import *
from ITSPrefixMiddleware import *
import ITSTranslate
import ITSHelpers

app = Flask(__name__, instance_relative_config=True)
app.wsgi_app = PrefixMiddleware(app.wsgi_app, prefix='/itr_api')
app.json_encoder = ITSJsonify.CustomJSONEncoder
Compress(app)
CORS(app)

@app.teardown_request
def teardown_request(exception=None):
    #stop all open database connections
    try:
     for key, dbengine in ITSRestAPIDB.db_engines_created.items():
        try:
            dbengine.dispose()
        except:
            pass
    except:
        pass

@app.errorhandler(500)
def internal_error(error):
    app_log.error("Internal server error 500 : %s", error)
    return "500 error"

@app.route('/test401')
def route_test401():
    return 'Not authorised', 401

# process the API request

@app.route('/')
def hello_world():
    return "A friendly greeting from the external ITR Rest API!", 200

# create a new test session with the test indicated and the norms requested
@app.route('/GetURLForPublicTest')
def get_url_for_public_test():
    company_id = request.headers['CompanyID']
    user_id = request.headers['UserID']
    external_api_token = request.headers['ExternalAPIToken']
    test_id = request.headers['TestID']
    reference_id = request.headers['ReferenceID']

    #optional headers
    try:
        norm_id_1 = "{00000000-0000-0000-0000-000000000000}"
        norm_id_1 = request.headers['NormID1']
    except:
        pass
    try:
        norm_id_2 = "{00000000-0000-0000-0000-000000000000}"
        norm_id_2 = request.headers['NormID2']
    except:
        pass
    try:
        norm_id_3 = "{00000000-0000-0000-0000-000000000000}"
        norm_id_3 = request.headers['NormID3']
    except:
        pass
    try:
        group_reference_id = "{00000000-0000-0000-0000-000000000000}"
        group_reference_id = request.headers['GroupReferenceID']
    except:
        pass
    try:
        session_description = "Session " + datetime.now().strftime("%B %d, %Y, %H:%M:%S")
        session_description = request.headers['Description']
    except:
        pass

    # check if the combination of company id, user id and external API token is correct. If not then return a forbidden
    # the external API key is in the PluginData field
    with ITSRestAPIDB.session_scope(company_id) as session:
        external_manager = session.query(ITSRestAPIORMExtensions.SecurityUser).filter(
            ITSRestAPIORMExtensions.SecurityUser.CompanyID == company_id).filter(
            ITSRestAPIORMExtensions.SecurityUser.ID == user_id).first()

        external_api_token_from_user = ""
        try:
            if external_manager is not None and external_manager.IsOfficeUser :
              external_api_token_from_user = json.loads(external_manager.PluginData)["ExternalAPIKey"]
        except:
            pass

        if external_api_token_from_user == external_api_token and external_api_token_from_user != "":
            # check if the External Test user exists with Email = "external_user_itr365.com"
            # if not add it
            hashed_password = hashlib.sha512(
                (str(uuid.uuid4()) + str(uuid.uuid4())).encode('utf-8')).hexdigest()
            external_test_testrun_user = session.query(ITSRestAPIORMExtensions.ClientPerson).filter(
                ITSRestAPIORMExtensions.ClientPerson.EMail == "external_user_itr365.com").first()
            if external_test_testrun_user is None:
                external_test_testrun_user = ITSRestAPIORMExtensions.ClientPerson()

                external_test_testrun_user.ID = uuid.uuid4()
                external_test_testrun_user.CompanyID = company_id
                external_test_testrun_user.IsOfficeUser = False
                external_test_testrun_user.EMail = "external_user_itr365.com"
                external_test_testrun_user.Password = hashed_password
                external_test_testrun_user.Active = True
                external_test_testrun_user.IsTestTakingUser = True
                session.add(external_test_testrun_user)

                with ITSRestAPIDB.session_scope("") as mastersession:
                    master_test_testrun_user = mastersession.query(ITSRestAPIORMExtensions.SecurityUser).filter(
                        ITSRestAPIORMExtensions.SecurityUser.Email == "external_user_itr365.com").filter(
                        ITSRestAPIORMExtensions.SecurityUser.CompanyID == company_id).delete()

            with ITSRestAPIDB.session_scope("") as mastersession:
                master_test_testrun_user = mastersession.query(ITSRestAPIORMExtensions.SecurityUser).filter(
                    ITSRestAPIORMExtensions.SecurityUser.Email == "external_user_itr365.com").filter(
                    ITSRestAPIORMExtensions.SecurityUser.CompanyID == company_id).first()
                if master_test_testrun_user is None:
                    #create the login for this external user
                    master_external_test_testrun_user = ITSRestAPIORMExtensions.SecurityUser()

                    master_external_test_testrun_user.ID = external_test_testrun_user.ID
                    master_external_test_testrun_user.CompanyID = company_id
                    master_external_test_testrun_user.IsOfficeUser = False
                    master_external_test_testrun_user.Email = "external_user_itr365.com"
                    master_external_test_testrun_user.UserName = "external_user_itr365.com"
                    master_external_test_testrun_user.Password = hashed_password
                    master_external_test_testrun_user.Active = True
                    master_external_test_testrun_user.IsTestTakingUser = True
                    mastersession.add(master_external_test_testrun_user)
            external_test_testrun_user.UserName = "external_user_itr365.com"

            # now check if the session exists
            # if it does not exist create it
            external_test_testrun_session = session.query(ITSRestAPIORMExtensions.ClientSession).filter(
                ITSRestAPIORMExtensions.ClientSession.ID == reference_id).first()
            if external_test_testrun_session is None:
                external_test_testrun_session = ITSRestAPIORMExtensions.ClientSession()
                external_test_testrun_session.ID = reference_id
                external_test_testrun_session.Active = True
                external_test_testrun_session.SessionType = 0
                external_test_testrun_session.Status = 10
                external_test_testrun_session.SessionState = "Ready"
                external_test_testrun_session.AllowedStartDateTime = datetime.now()
                external_test_testrun_session.AllowedEndDateTime = datetime(2100, 1, 1)
                external_test_testrun_session.PersonID = external_test_testrun_user.ID
                external_test_testrun_session.GroupID = group_reference_id
                external_test_testrun_session.GroupSessionID = "{00000000-0000-0000-0000-000000000000}"
                session.add(external_test_testrun_session)
            external_test_testrun_session.Description = session_description

            # check if this test is in the session
            # if it is not in the session then add it
            # this way you can create a single session with multiple tests if you really want that
            external_test_testrun_session_test = session.query(ITSRestAPIORMExtensions.ClientSessionTest).filter(
                ITSRestAPIORMExtensions.ClientSessionTest.SessionID == reference_id).filter(
                ITSRestAPIORMExtensions.ClientSessionTest.TestID == test_id).first()
            if external_test_testrun_session_test is None:
                external_test_testrun_session_test = ITSRestAPIORMExtensions.ClientSessionTest()
                external_test_testrun_session_test.ID = uuid.uuid4()
                external_test_testrun_session_test.TestID = test_id
                external_test_testrun_session_test.Status = 10
                external_test_testrun_session_test.HowTheTestIsTaken = 10
                external_test_testrun_session_test.NormID1 = norm_id_1
                external_test_testrun_session_test.NormID2 = norm_id_2
                external_test_testrun_session_test.NormID3 = norm_id_3
                external_test_testrun_session_test.Scores = "{}"
                external_test_testrun_session_test.Results = "{}"
                external_test_testrun_session_test.PersID = external_test_testrun_user.ID
                external_test_testrun_session_test.SessionID = reference_id
                external_test_testrun_session_test.TestLanguage = ""
                session.add(external_test_testrun_session_test)

            # check if a login token exists for this user 
            # if there already is an active token for this ReferenceID then return that token
            token = ITSRestAPILogin.create_session_token("external_user_itr365.com", company_id,
                                                         ITSRestAPILogin.LoginTokenType.regular_session)

            if external_test_testrun_session.Status < 30:
                return "?TestTakingOnly=Y&Token=" + token + "&CompanyID=" + company_id, 200
            else:
                return "?TestTakingOnly=Y&Token=" + token + "&CompanyID=" + company_id, 204
        else:
            return "The external API token for this user_id does not exist or is not correct", 403

if __name__ == '__main__':
    # app.debug = True
    # MET FLASK app.run()
    # app.run(debug=True)
    serve(app.wsgi_app, threads = 25, listen="*:1443")