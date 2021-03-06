#!/usr/bin/env python

"""models.py

Udacity conference server-side Python App Engine data & ProtoRPC models

$Id: models.py,v 1.1 2014/05/24 22:01:10 wesc Exp $

created/forked from conferences.py by wesc on 2014 may 24

"""

__author__ = 'wesc+api@google.com (Wesley Chun)'

import httplib
import endpoints
from protorpc import messages
from google.appengine.ext import ndb
from collections import Counter

class ConflictException(endpoints.ServiceException):
    """ConflictException -- exception mapped to HTTP 409 response"""
    http_status = httplib.CONFLICT

class Profile(ndb.Model):
    """Profile -- User profile object"""
    displayName = ndb.StringProperty()
    mainEmail = ndb.StringProperty()
    teeShirtSize = ndb.StringProperty(default='NOT_SPECIFIED')
    conferenceKeysToAttend = ndb.StringProperty(repeated=True)
    wishlist = ndb.StringProperty(repeated=True)

class ProfileMiniForm(messages.Message):
    """ProfileMiniForm -- update Profile form message"""
    displayName = messages.StringField(1)
    teeShirtSize = messages.EnumField('TeeShirtSize', 2)

class ProfileForm(messages.Message):
    """ProfileForm -- Profile outbound form message"""
    displayName = messages.StringField(1)
    mainEmail = messages.StringField(2)
    teeShirtSize = messages.EnumField('TeeShirtSize', 3)
    conferenceKeysToAttend = messages.StringField(4, repeated=True)
    wishlist = messages.StringField(5, repeated=True)

class StringMessage(messages.Message):
    """StringMessage-- outbound (single) string message"""
    data = messages.StringField(1, required=True)

class BooleanMessage(messages.Message):
    """BooleanMessage-- outbound Boolean value message"""
    data = messages.BooleanField(1)

class Conference(ndb.Model):
    """Conference -- Conference object"""
    name            = ndb.StringProperty(required=True)
    description     = ndb.StringProperty()
    organizerUserId = ndb.StringProperty()
    topics          = ndb.StringProperty(repeated=True)
    city            = ndb.StringProperty()
    startDate       = ndb.DateProperty()
    month           = ndb.IntegerProperty() # TODO: do we need for indexing like Java?
    endDate         = ndb.DateProperty()
    maxAttendees    = ndb.IntegerProperty()
    seatsAvailable  = ndb.IntegerProperty()

class ConferenceForm(messages.Message):
    """ConferenceForm -- Conference outbound form message"""
    name            = messages.StringField(1)
    description     = messages.StringField(2)
    organizerUserId = messages.StringField(3)
    topics          = messages.StringField(4, repeated=True)
    city            = messages.StringField(5)
    startDate       = messages.StringField(6) #DateTimeField()
    month           = messages.IntegerField(7)
    maxAttendees    = messages.IntegerField(8)
    seatsAvailable  = messages.IntegerField(9)
    endDate         = messages.StringField(10) #DateTimeField()
    websafeKey      = messages.StringField(11)
    organizerDisplayName = messages.StringField(12)

class ConferenceForms(messages.Message):
    """ConferenceForms -- multiple Conference outbound form message"""
    items = messages.MessageField(ConferenceForm, 1, repeated=True)

class TeeShirtSize(messages.Enum):
    """TeeShirtSize -- t-shirt size enumeration value"""
    NOT_SPECIFIED = 1
    XS_M = 2
    XS_W = 3
    S_M = 4
    S_W = 5
    M_M = 6
    M_W = 7
    L_M = 8
    L_W = 9
    XL_M = 10
    XL_W = 11
    XXL_M = 12
    XXL_W = 13
    XXXL_M = 14
    XXXL_W = 15

class ConferenceQueryForm(messages.Message):
    """ConferenceQueryForm -- Conference query inbound form message"""
    field = messages.StringField(1)
    operator = messages.StringField(2)
    value = messages.StringField(3)

class ConferenceQueryForms(messages.Message):
    """ConferenceQueryForms -- multiple ConferenceQueryForm inbound form message"""
    filters = messages.MessageField(ConferenceQueryForm, 1, repeated=True)

class Session(ndb.Model):
    """Session -- Session object"""
    name            = ndb.StringProperty(required=True)
    highlights      = ndb.StringProperty()
    speaker         = ndb.StringProperty()
    duration        = ndb.IntegerProperty()
    typeOfSession   = ndb.StringProperty(default='NOT_SPECIFIED')
    dayofConf       = ndb.IntegerProperty(default=1)
    startTime       = ndb.IntegerProperty()
    wishlisted      = ndb.IntegerProperty(default=0)

    @classmethod
    def countspeakers(self, conf_key):
        """
        Return the speaker and the number of sessions speaker is in
        given a confence.
        """
        speakers = [session.speaker for session in self.query(ancestor=\
                    conf_key, projection=[Session.speaker])]
        # Returns array [('speakers name', 'number of session speaker is in' )]
        speakerCount =  Counter(speakers)
        return speakerCount.most_common(1)[0]


class SessionForm(messages.Message):
    """
    SessionForm -- Session outbound form message
    Excluded a websafeSessionKey
    """
    name            = messages.StringField(1)
    highlights      = messages.StringField(2)
    speaker         = messages.StringField(3)
    duration        = messages.IntegerField(4)
    typeOfSession   = messages.EnumField('TypeOfSession', 5)
    startTime       = messages.IntegerField(6)
    dayofConf       = messages.IntegerField(7)

class TypeOfSession(messages.Enum):
    """TypeOfSession -- Session types enumeration value"""
    NOT_SPECIFIED = 1
    LECTURE = 2
    KEYNOTE = 3
    WORKSHOP = 4
    PARTY = 5
    SEMINARS = 6
    MEETUPS = 7
    EXHIBITION = 8
    PRESENTATIONS = 9

class SessionForms(messages.Message):
    """SessionForms -- multiple Session outbound form message"""
    sessions = messages.MessageField(SessionForm, 1, repeated=True)

class SessionQueryForm(messages.Message):
    """SessionQueryForm -- Session query inbound form message"""
    field = messages.StringField(1)
    operator = messages.StringField(2)
    value = messages.StringField(3)

class SpeakerSessionQueryForm(messages.Message):
    """SpeakerSessionQueryForm -- Session query inbound form message"""
    speaker = messages.StringField(1)

class SessionQueryForms(messages.Message):
    """SessionQueryForms -- multiple SessionQueryForm inbound form message"""
    filters = messages.MessageField(SessionQueryForm, 1, repeated=True)

class FeatureSpeaker(messages.Message):
    """FeatureSpeaker -- FeatureSpeaker outbound form message """
    name = messages.StringField(1)
    conf_name = messages.StringField(2)
    sessions = messages.StringField(3, repeated=True)
