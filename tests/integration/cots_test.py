# coding: utf8

# Copyright (c) 2001-2018, Canal TP and/or its affiliates. All rights reserved.
#
# This file is part of Navitia,
#     the software to build cool stuff with public transport.
#
# Hope you'll enjoy and contribute to this project,
#     powered by Canal TP (www.canaltp.fr).
# Help us simplify mobility and open public transport:
#     a non ending quest to the responsive locomotion way of traveling!
#
# LICENCE: This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
#
# Stay tuned using
# twitter @navitia
# IRC #navitia on freenode
# https://groups.google.com/d/forum/navitia
# www.navitia.io
from datetime import datetime
from pytz import utc

import pytest

from tests.check_utils import api_post, api_get
from kirin import app
from tests import mock_navitia
from tests.check_utils import get_fixture_data
from kirin.core.model import RealTimeUpdate, TripUpdate, StopTimeUpdate
from tests.integration.utils_cots_test import requests_mock_cause_message
from tests.integration.utils_sncf_test import check_db_96231_delayed, check_db_john_trip_removal, \
    check_db_96231_trip_removal, check_db_6113_trip_removal, check_db_6114_trip_removal, check_db_96231_normal, \
    check_db_840427_partial_removal, check_db_96231_partial_removal


@pytest.fixture(scope='function', autouse=True)
def navitia(monkeypatch):
    """
    Mock all calls to navitia for this fixture
    """
    monkeypatch.setattr('navitia_wrapper._NavitiaWrapper.query', mock_navitia.mock_navitia_query)


@pytest.fixture(scope='function')
def mock_rabbitmq(monkeypatch):
    """
    Mock all calls to navitia for this fixture
    """
    from mock import MagicMock

    mock_amqp = MagicMock()
    monkeypatch.setattr('kombu.messaging.Producer.publish', mock_amqp)

    return mock_amqp


@pytest.fixture(scope='function', autouse=True)
def mock_cause_message(requests_mock):
    """
    Mock all calls to cause message sub-service for this fixture
    """
    return requests_mock_cause_message(requests_mock)


def test_wrong_cots_post():
    """
    simple json post on the api
    """
    res, status = api_post('/cots', check=False, data='{}')

    assert status == 400

    print res.get('error') == 'invalid'


def test_cots_post_no_data():
    """
    when no data is given, we got a 400 error
    """
    tester = app.test_client()
    resp = tester.post('/cots')
    assert resp.status_code == 400

    with app.app_context():
        assert len(RealTimeUpdate.query.all()) == 0
        assert len(TripUpdate.query.all()) == 0
        assert len(StopTimeUpdate.query.all()) == 0


def test_cots_simple_post(mock_rabbitmq):
    """
    simple COTS post should be stored in db as a RealTimeUpdate
    """
    cots_file = get_fixture_data('cots_train_96231_delayed.json')
    res = api_post('/cots', data=cots_file)
    assert res == 'OK'

    with app.app_context():
        rtu_array = RealTimeUpdate.query.all()
        assert len(rtu_array) == 1
        rtu = rtu_array[0]
        assert '-' in rtu.id
        assert rtu.received_at
        assert rtu.status == 'OK'
        assert rtu.error is None
        assert rtu.contributor == 'realtime.cots'
        assert rtu.connector == 'cots'
        assert 'listePointDeParcours' in rtu.raw_data
    assert mock_rabbitmq.call_count == 1


def test_save_bad_raw_cots():
    """
    send a bad formatted COTS, the bad raw COTS should be saved in db
    """
    bad_cots = get_fixture_data('bad_cots.json')
    res = api_post('/cots', data=bad_cots, check=False)
    assert res[1] == 400
    assert res[0]['message'] == 'Invalid arguments'
    with app.app_context():
        assert len(RealTimeUpdate.query.all()) == 1
        assert RealTimeUpdate.query.first().status == 'KO'
        assert RealTimeUpdate.query.first().error == \
            'invalid json, impossible to find "numeroCourse" in json dict {"bad":"one","cots":"toto"}'
        assert RealTimeUpdate.query.first().raw_data == bad_cots


def test_cots_delayed_simple_post(mock_rabbitmq):
    """
    simple delayed stops post
    """
    cots_96231 = get_fixture_data('cots_train_96231_delayed.json')
    res = api_post('/cots', data=cots_96231)
    assert res == 'OK'

    with app.app_context():
        assert len(RealTimeUpdate.query.all()) == 1
        assert len(TripUpdate.query.all()) == 1
        assert len(StopTimeUpdate.query.all()) == 6
        db_trip_delayed = TripUpdate.find_by_dated_vj('trip:OCETrainTER-87212027-85000109-3:11859',
                                                      datetime(2015, 9, 21, 15, 21, tzinfo=utc))
        assert db_trip_delayed.stop_time_updates[4].message is None
    check_db_96231_delayed(contributor='realtime.cots')
    assert mock_rabbitmq.call_count == 1


def test_cots_delayed_then_ok(mock_rabbitmq):
    """
    We delay a stop, then the vj is back on time
    """
    cots_96231 = get_fixture_data('cots_train_96231_delayed.json')
    res = api_post('/cots', data=cots_96231)
    assert res == 'OK'

    with app.app_context():
        assert len(RealTimeUpdate.query.all()) == 1
        assert len(TripUpdate.query.all()) == 1
        assert len(StopTimeUpdate.query.all()) == 6
        assert RealTimeUpdate.query.first().status == 'OK'
    check_db_96231_delayed(contributor='realtime.cots')
    assert mock_rabbitmq.call_count == 1

    cots_96231 = get_fixture_data('cots_train_96231_normal.json')
    res = api_post('/cots', data=cots_96231)
    assert res == 'OK'

    with app.app_context():
        assert len(RealTimeUpdate.query.all()) == 2
        assert len(TripUpdate.query.all()) == 1
        assert len(StopTimeUpdate.query.all()) == 6
    check_db_96231_normal(contributor='realtime.cots')
    assert mock_rabbitmq.call_count == 2


def test_cots_delayed_post_twice(mock_rabbitmq):
    """
    double delayed stops post
    """
    cots_96231 = get_fixture_data('cots_train_96231_delayed.json')
    res = api_post('/cots', data=cots_96231)
    assert res == 'OK'
    res = api_post('/cots', data=cots_96231)
    assert res == 'OK'

    with app.app_context():
        assert len(RealTimeUpdate.query.all()) == 2
        assert len(TripUpdate.query.all()) == 1
        assert len(StopTimeUpdate.query.all()) == 6
    check_db_96231_delayed(contributor='realtime.cots')
    # the rabbit mq has to have been called twice
    assert mock_rabbitmq.call_count == 2


def test_cots_trip_delayed_then_removal(mock_rabbitmq):
    """
    post delayed stops then trip removal on the same trip
    """
    cots_96231_delayed = get_fixture_data('cots_train_96231_delayed.json')
    res = api_post('/cots', data=cots_96231_delayed)
    assert res == 'OK'
    cots_96231_trip_removal = get_fixture_data('cots_train_96231_trip_removal.json')
    res = api_post('/cots', data=cots_96231_trip_removal)
    assert res == 'OK'

    with app.app_context():
        assert len(RealTimeUpdate.query.all()) == 2
        assert len(TripUpdate.query.all()) == 1
        assert len(StopTimeUpdate.query.all()) == 0
    check_db_96231_trip_removal()
    # the rabbit mq has to have been called twice
    assert mock_rabbitmq.call_count == 2


def test_cots_trip_delayed_then_partial_removal(mock_rabbitmq):
    """
    post delayed stops then trip removal on the same trip
    """
    cots_96231_delayed = get_fixture_data('cots_train_96231_delayed.json')
    res = api_post('/cots', data=cots_96231_delayed)
    assert res == 'OK'
    cots_96231_partial_removal = get_fixture_data('cots_train_96231_partial_removal.json')
    res = api_post('/cots', data=cots_96231_partial_removal)
    assert res == 'OK'

    with app.app_context():
        assert len(RealTimeUpdate.query.all()) == 2
        assert len(TripUpdate.query.all()) == 1
        assert len(StopTimeUpdate.query.all()) == 6
        assert RealTimeUpdate.query.first().status == 'OK'
    check_db_96231_partial_removal(contributor='realtime.cots')
    # the rabbit mq has to have been called twice
    assert mock_rabbitmq.call_count == 2


def test_cots_trip_removal_simple_post(mock_rabbitmq):
    """
    simple trip removal post
    """
    cots_6113 = get_fixture_data('cots_train_6113_trip_removal.json')
    res = api_post('/cots', data=cots_6113)
    assert res == 'OK'

    with app.app_context():
        assert len(RealTimeUpdate.query.all()) == 1
        assert len(TripUpdate.query.all()) == 1
        assert len(StopTimeUpdate.query.all()) == 0
    check_db_6113_trip_removal()
    assert mock_rabbitmq.call_count == 1


def test_cots_delayed_and_trip_removal_post(mock_rabbitmq):
    """
    post delayed stops on one trip then trip removal on another
    """
    cots_96231 = get_fixture_data('cots_train_96231_delayed.json')
    res = api_post('/cots', data=cots_96231)
    assert res == 'OK'

    cots_6113 = get_fixture_data('cots_train_6113_trip_removal.json')
    res = api_post('/cots', data=cots_6113)
    assert res == 'OK'

    with app.app_context():
        assert len(RealTimeUpdate.query.all()) == 2
        assert len(TripUpdate.query.all()) == 2
        assert len(StopTimeUpdate.query.all()) == 6
    check_db_96231_delayed(contributor='realtime.cots')
    check_db_6113_trip_removal()
    # the rabbit mq has to have been called twice
    assert mock_rabbitmq.call_count == 2


def test_cots_trip_removal_post_twice(mock_rabbitmq):
    """
    double trip removal post
    """
    cots_6113 = get_fixture_data('cots_train_6113_trip_removal.json')
    res = api_post('/cots', data=cots_6113)
    assert res == 'OK'
    res = api_post('/cots', data=cots_6113)
    assert res == 'OK'

    with app.app_context():
        assert len(RealTimeUpdate.query.all()) == 2
        assert len(TripUpdate.query.all()) == 1
        assert len(StopTimeUpdate.query.all()) == 0
    check_db_6113_trip_removal()
    # the rabbit mq has to have been called twice
    assert mock_rabbitmq.call_count == 2


def test_cots_trip_with_parity(mock_rabbitmq):
    """
    a trip with a parity has been impacted, there should be 2 VJ impacted
    """
    cots_6113 = get_fixture_data('cots_train_6113_trip_removal.json')
    cots_6113_14 = cots_6113.replace('"numeroCourse": "006113",',
                                     '"numeroCourse": "006113/4",')
    res = api_post('/cots', data=cots_6113_14)
    assert res == 'OK'

    with app.app_context():
        assert len(RealTimeUpdate.query.all()) == 1

        # there should be 2 trip updated,
        # - trip:OCETGV-87686006-87751008-2:25768-2 for the headsign 6114
        # - trip:OCETGV-87686006-87751008-2:25768 for the headsign 6113

        assert len(TripUpdate.query.all()) == 2
        assert len(StopTimeUpdate.query.all()) == 0

    check_db_6113_trip_removal()
    check_db_6114_trip_removal()

    assert mock_rabbitmq.call_count == 1


def test_cots_trip_with_parity_one_unknown_vj(mock_rabbitmq):
    """
    a trip with a parity has been impacted, but the train 6112 is not known by navitia
    there should be only the train 6113 impacted
    """
    cots_6113 = get_fixture_data('cots_train_6113_trip_removal.json')
    cots_6112_13 = cots_6113.replace('"numeroCourse": "006113",',
                                     '"numeroCourse": "006112/3",')
    res = api_post('/cots', data=cots_6112_13)
    assert res == 'OK'

    with app.app_context():
        assert len(RealTimeUpdate.query.all()) == 1
        assert len(TripUpdate.query.all()) == 1
        assert len(StopTimeUpdate.query.all()) == 0

    check_db_6113_trip_removal()

    assert mock_rabbitmq.call_count == 1


def test_cots_trip_unknown_vj(mock_rabbitmq):
    """
    a trip with a parity has been impacted, but the train 6112 is not known by navitia
    there should be only the train 6113 impacted
    """
    cots_6113 = get_fixture_data('cots_train_6113_trip_removal.json')
    cots_6112 = cots_6113.replace('"numeroCourse": "006113",',
                                  '"numeroCourse": "006112",')

    res = api_post('/cots', data=cots_6112, check=False)
    assert res[1] == 404
    assert res[0]['error'] == 'no train found for headsign(s) 006112'
    with app.app_context():
        assert len(RealTimeUpdate.query.all()) == 1
        assert len(TripUpdate.query.all()) == 0
        assert len(StopTimeUpdate.query.all()) == 0
        assert RealTimeUpdate.query.first().status == 'KO'
        assert RealTimeUpdate.query.first().error == \
            'no train found for headsign(s) 006112'
        assert RealTimeUpdate.query.first().raw_data == cots_6112

    status = api_get('/status')
    assert '-' in status['last_update']['realtime.cots']  # only check it's a date
    assert status['last_valid_update'] == {}
    assert status['last_update_error']['realtime.cots'] == 'no train found for headsign(s) 006112'

    assert mock_rabbitmq.call_count == 0


def test_cots_two_trip_removal_one_post(mock_rabbitmq):
    """
    post one COTS trip removal on two trips
    (navitia mock returns 2 vj for 'JOHN' headsign)
    """
    cots_john_trip_removal = get_fixture_data('cots_train_JOHN_trip_removal.json')
    res = api_post('/cots', data=cots_john_trip_removal)
    assert res == 'OK'

    with app.app_context():
        assert len(RealTimeUpdate.query.all()) == 1
        assert len(TripUpdate.query.all()) == 2
        assert len(StopTimeUpdate.query.all()) == 0
    check_db_john_trip_removal()
    # the rabbit mq has to have been called twice
    assert mock_rabbitmq.call_count == 1


def test_cots_two_trip_removal_post_twice(mock_rabbitmq):
    """
    post twice COTS trip removal on two trips
    """
    cots_john_trip_removal = get_fixture_data('cots_train_JOHN_trip_removal.json')
    res = api_post('/cots', data=cots_john_trip_removal)
    assert res == 'OK'
    res = api_post('/cots', data=cots_john_trip_removal)
    assert res == 'OK'

    with app.app_context():
        assert len(RealTimeUpdate.query.all()) == 2
        assert len(TripUpdate.query.all()) == 2
        assert len(StopTimeUpdate.query.all()) == 0
    check_db_john_trip_removal()
    # the rabbit mq has to have been called twice
    assert mock_rabbitmq.call_count == 2


def test_cots_partial_removal(mock_rabbitmq):
    """
    the trip 840427 has been partialy deleted

    Normally there are 7 stops in this VJ, but 4 (Chaumont, Bar-sur-Aube, Vendeuvre and Troyes) have been removed
    """
    cots_080427 = get_fixture_data('cots_train_840427_partial_removal.json')
    res = api_post('/cots', data=cots_080427)
    assert res == 'OK'

    with app.app_context():
        assert len(RealTimeUpdate.query.all()) == 1
        assert len(TripUpdate.query.all()) == 1
        assert len(StopTimeUpdate.query.all()) == 7
        assert RealTimeUpdate.query.first().status == 'OK'
    check_db_840427_partial_removal(contributor='realtime.cots')
    assert mock_rabbitmq.call_count == 1
