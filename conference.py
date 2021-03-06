#!/usr/bin/env python

"""
conference.py -- Udacity conference server-side Python App Engine API;
    uses Google Cloud Endpoints

$Id: conference.py,v 1.25 2014/05/24 23:42:19 wesc Exp wesc $

created by wesc on 2014 apr 21

"""

__author__ = 'wesc+api@google.com (Wesley Chun)'


from datetime import datetime

import endpoints
from protorpc import messages
from protorpc import message_types
from protorpc import remote

from google.appengine.api import memcache
from google.appengine.api import taskqueue
from google.appengine.ext import ndb

from models import ConflictException
from models import Profile
from models import ProfileMiniForm
from models import ProfileForm
from models import StringMessage
from models import BooleanMessage
from models import Conference
from models import ConferenceForm
from models import ConferenceForms
from models import ConferenceQueryForm
from models import ConferenceQueryForms
from models import TeeShirtSize
from models import Session
from models import SessionForm
from models import SessionForms
from models import SessionQueryForm
from models import SessionQueryForms
from models import TypeOfSession
from models import FeatureSpeaker
from models import SpeakerSessionQueryForm

from settings import WEB_CLIENT_ID
from settings import ANDROID_CLIENT_ID
from settings import IOS_CLIENT_ID
from settings import ANDROID_AUDIENCE

from utils import getUserId

EMAIL_SCOPE = endpoints.EMAIL_SCOPE
API_EXPLORER_CLIENT_ID = endpoints.API_EXPLORER_CLIENT_ID
MEMCACHE_ANNOUNCEMENTS_KEY = "RECENT_ANNOUNCEMENTS"
SPEAKER_ANNOUNCEMENTS_KEY = "FEATURED_SPEAKER_ FOR_"
ANNOUNCEMENT_TPL = ('Last chance to attend! The following conferences '
                    'are nearly sold out: %s')
ANNOUNCEMENT_SPK = ('Hear %s speak at %s. Featured during these sessions: %s.')
# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

DEFAULTS = {
    "city": "Default City",
    "maxAttendees": 0,
    "seatsAvailable": 0,
    "topics": ["Default", "Topic"],
}

OPERATORS = {
            'EQ':   '=',
            'GT':   '>',
            'GTEQ': '>=',
            'LT':   '<',
            'LTEQ': '<=',
            'NE':   '!='
            }

FIELDS =   {
            'CITY': 'city',
            'TOPIC': 'topics',
            'MONTH': 'month',
            'MAX_ATTENDEES': 'maxAttendees',
            'TYPE': 'typeOfSession',
            'SPEAKER': 'speaker',
            'START_TIME': 'startTime',
            'DURATION': 'duration',
            'DAY': 'dayofConf',
            }

CONF_GET_REQUEST = endpoints.ResourceContainer(
    message_types.VoidMessage,
    websafeConferenceKey=messages.StringField(1),
)

CONF_POST_REQUEST = endpoints.ResourceContainer(
    ConferenceForm,
    websafeConferenceKey=messages.StringField(1),
)

SESS_POST_REQUEST = endpoints.ResourceContainer(
    SessionForm,
    websafeConferenceKey=messages.StringField(1),
)

SESSIONS_POST_REQUEST = endpoints.ResourceContainer(
    SessionForms,
    websafeConferenceKey=messages.StringField(1),
)

QUERY_POST_REQUEST = endpoints.ResourceContainer(
    SessionQueryForms,
    websafeConferenceKey=messages.StringField(1),
)

SINGLE_POST_REQUEST = endpoints.ResourceContainer(
    SessionQueryForm,
    websafeConferenceKey=messages.StringField(1),
)

WISHLIST_POST_REQUEST = endpoints.ResourceContainer(
    message_types.VoidMessage,
    websafeSessionsKey=messages.StringField(1),
)


# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -


@endpoints.api(name='conference', version='v1', audiences=[ANDROID_AUDIENCE],
    allowed_client_ids=[WEB_CLIENT_ID, API_EXPLORER_CLIENT_ID, ANDROID_CLIENT_ID, IOS_CLIENT_ID],
    scopes=[EMAIL_SCOPE])
class ConferenceApi(remote.Service):
    """Conference API v0.1"""

# - - - Conference objects - - - - - - - - - - - - - - - - -

    def _copyConferenceToForm(self, conf, displayName):
        """Copy relevant fields from Conference to ConferenceForm."""
        cf = ConferenceForm()
        for field in cf.all_fields():
            if hasattr(conf, field.name):
                # convert Date to date string; just copy others
                if field.name.endswith('Date'):
                    setattr(cf, field.name, str(getattr(conf, field.name)))
                else:
                    setattr(cf, field.name, getattr(conf, field.name))
            elif field.name == "websafeKey":
                setattr(cf, field.name, conf.key.urlsafe())
        if displayName:
            setattr(cf, 'organizerDisplayName', displayName)
        cf.check_initialized()
        return cf

    def _createConferenceObject(self, request):
        """Create or update Conference object, returning ConferenceForm/request."""
        # preload necessary data items
        user = endpoints.get_current_user()
        if not user:
            raise endpoints.UnauthorizedException('Authorization required')
        user_id = getUserId(user)

        if not request.name:
            raise endpoints.BadRequestException("Conference 'name' field required")

        # copy ConferenceForm/ProtoRPC Message into dict
        data = {field.name: getattr(request, field.name) for field in request.all_fields()}
        del data['websafeKey']
        del data['organizerDisplayName']

        # add default values for those missing (both data model & outbound Message)
        for df in DEFAULTS:
            if data[df] in (None, []):
                data[df] = DEFAULTS[df]
                setattr(request, df, DEFAULTS[df])

        # convert dates from strings to Date objects; set month based on start_date
        if data['startDate']:
            data['startDate'] = datetime.strptime(data['startDate'][:10], "%Y-%m-%d").date()
            data['month'] = data['startDate'].month
        else:
            data['month'] = 0
        if data['endDate']:
            data['endDate'] = datetime.strptime(data['endDate'][:10], "%Y-%m-%d").date()

        # set seatsAvailable to be same as maxAttendees on creation
        if data["maxAttendees"] > 0:
            data["seatsAvailable"] = data["maxAttendees"]
        # generate Profile Key based on user ID and Conference
        # ID based on Profile key get Conference key from ID
        p_key = ndb.Key(Profile, user_id)
        c_id = Conference.allocate_ids(size=1, parent=p_key)[0]
        c_key = ndb.Key(Conference, c_id, parent=p_key)
        data['key'] = c_key
        data['organizerUserId'] = request.organizerUserId = user_id

        # create Conference, send email to organizer confirming
        # creation of Conference & return (modified) ConferenceForm
        Conference(**data).put()
        taskqueue.add(params={'email': user.email(),
            'conferenceInfo': repr(request)},
            url='/tasks/send_confirmation_email'
        )
        return request


    @ndb.transactional()
    def _updateConferenceObject(self, request):
        user = endpoints.get_current_user()
        if not user:
            raise endpoints.UnauthorizedException('Authorization required')
        user_id = getUserId(user)

        # copy ConferenceForm/ProtoRPC Message into dict
        data = {field.name: getattr(request, field.name) for field in request.all_fields()}

        # update existing conference
        conf = ndb.Key(urlsafe=request.websafeConferenceKey).get()
        # check that conference exists
        if not conf:
            raise endpoints.NotFoundException(
                'No conference found with key: %s' % request.websafeConferenceKey)

        # check that user is owner
        if user_id != conf.organizerUserId:
            raise endpoints.ForbiddenException(
                'Only the owner can update the conference.')

        # Not getting all the fields, so don't create a new object; just
        # copy relevant fields from ConferenceForm to Conference object
        for field in request.all_fields():
            data = getattr(request, field.name)
            # only copy fields where we get data
            if data not in (None, []):
                # special handling for dates (convert string to Date)
                if field.name in ('startDate', 'endDate'):
                    data = datetime.strptime(data, "%Y-%m-%d").date()
                    if field.name == 'startDate':
                        conf.month = data.month
                # write to Conference object
                setattr(conf, field.name, data)
        conf.put()
        prof = ndb.Key(Profile, user_id).get()
        return self._copyConferenceToForm(conf, getattr(prof, 'displayName'))


    @endpoints.method(ConferenceForm, ConferenceForm, path='conference',
            http_method='POST', name='createConference')
    def createConference(self, request):
        """Create new conference."""
        return self._createConferenceObject(request)


    @endpoints.method(CONF_POST_REQUEST, ConferenceForm,
            path='conference/{websafeConferenceKey}',
            http_method='PUT', name='updateConference')
    def updateConference(self, request):
        """Update conference w/provided fields & return w/updated info."""
        return self._updateConferenceObject(request)


    @endpoints.method(CONF_GET_REQUEST, ConferenceForm,
            path='conference/{websafeConferenceKey}',
            http_method='GET', name='getConference')
    def getConference(self, request):
        """Return requested conference (by websafeConferenceKey)."""
        # get Conference object from request; bail if not found
        conf = ndb.Key(urlsafe=request.websafeConferenceKey).get()
        if not conf:
            raise endpoints.NotFoundException(
                'No conference found with key: %s' % request.websafeConferenceKey)
        prof = conf.key.parent().get()
        # return ConferenceForm
        return self._copyConferenceToForm(conf, getattr(prof, 'displayName'))


    @endpoints.method(message_types.VoidMessage, ConferenceForms,
            path='getConferencesCreated',
            http_method='POST', name='getConferencesCreated')
    def getConferencesCreated(self, request):
        """Return conferences created by user."""
        # make sure user is authed
        user = endpoints.get_current_user()
        if not user:
            raise endpoints.UnauthorizedException('Authorization required')
        user_id = getUserId(user)

        # create ancestor query for all key matches for this user
        confs = Conference.query(ancestor=ndb.Key(Profile, user_id))
        prof = ndb.Key(Profile, user_id).get()
        # return set of ConferenceForm objects per Conference
        return ConferenceForms(
            items=[self._copyConferenceToForm(conf, getattr(prof, 'displayName')) for conf in confs]
        )


    def _getQuery(self, request):
        """Return formatted query from the submitted filters."""
        q = Conference.query()

        inequality_filter, filters = self._formatFilters(request.filters)

        # If exists, sort on inequality filter first
        if not inequality_filter:
            q = q.order(Conference.name)
        else:
            q = q.order(ndb.GenericProperty(inequality_filter))
            q = q.order(Conference.name)
        for filtr in filters:
            if filtr["field"] in ["month", "maxAttendees"]:
                filtr["value"] = int(filtr["value"])
            formatted_query = ndb.query.FilterNode(filtr["field"], filtr["operator"], filtr["value"])
            q = q.filter(formatted_query)
        return q


    def _formatFilters(self, filters):
        """Parse, check validity and format user supplied filters."""
        formatted_filters = []
        inequality_field = None

        for f in filters:
            filtr = {field.name: getattr(f, field.name) for field in f.all_fields()}

            try:
                filtr["field"] = FIELDS[filtr["field"]]
                filtr["operator"] = OPERATORS[filtr["operator"]]
            except KeyError:
                raise endpoints.BadRequestException("Filter contains invalid field or operator.")

            # Every operation except "=" is an inequality
            if filtr["operator"] != "=":
                # check if inequality operation has been used in previous filters
                # disallow the filter if inequality was performed on a different field before
                # track the field on which the inequality operation is performed
                if inequality_field and inequality_field != filtr["field"]:
                    raise endpoints.BadRequestException("Inequality filter is allowed on only one field.")
                else:
                    inequality_field = filtr["field"]

            formatted_filters.append(filtr)
        return (inequality_field, formatted_filters)


    @endpoints.method(ConferenceQueryForms, ConferenceForms,
            path='queryConferences',
            http_method='POST',
            name='queryConferences')
    def queryConferences(self, request):
        """Query for conferences."""
        conferences = self._getQuery(request)

        # need to fetch organiser displayName from profiles
        # get all keys and use get_multi for speed
        organisers = [(ndb.Key(Profile, conf.organizerUserId)) for conf in conferences]
        profiles = ndb.get_multi(organisers)

        # put display names in a dict for easier fetching
        names = {}
        for profile in profiles:
            names[profile.key.id()] = profile.displayName

        # return individual ConferenceForm object per Conference
        return ConferenceForms(
                items=[self._copyConferenceToForm(conf, names[conf.organizerUserId]) for conf in \
                conferences]
        )


# - - - Profile objects - - - - - - - - - - - - - - - - - - -

    def _copyProfileToForm(self, prof):
        """Copy relevant fields from Profile to ProfileForm."""
        # copy relevant fields from Profile to ProfileForm
        pf = ProfileForm()
        for field in pf.all_fields():
            if hasattr(prof, field.name):
                # convert t-shirt string to Enum; just copy others
                if field.name == 'teeShirtSize':
                    setattr(pf, field.name, getattr(TeeShirtSize, getattr(prof, field.name)))
                else:
                    setattr(pf, field.name, getattr(prof, field.name))
        pf.check_initialized()
        return pf


    def _getProfileFromUser(self):
        """Return user Profile from datastore, creating new one if non-existent."""
        # make sure user is authed
        user = endpoints.get_current_user()
        if not user:
            raise endpoints.UnauthorizedException('Authorization required')

        # get Profile from datastore
        user_id = getUserId(user)
        p_key = ndb.Key(Profile, user_id)
        profile = p_key.get()
        # create new Profile if not there
        if not profile:
            profile = Profile(
                key = p_key,
                displayName = user.nickname(),
                mainEmail= user.email(),
                teeShirtSize = str(TeeShirtSize.NOT_SPECIFIED),
            )
            profile.put()

        return profile      # return Profile


    def _doProfile(self, save_request=None):
        """Get user Profile and return to user, possibly updating it first."""
        prof = self._getProfileFromUser()

        # if saveProfile(), process user-modifyable fields
        if save_request:
            for field in ('displayName', 'teeShirtSize'):
                if hasattr(save_request, field):
                    val = getattr(save_request, field)
                    if val:
                        setattr(prof, field, str(val))
                        # if field == 'teeShirtSize':
                        #    setattr(prof, field, str(val).upper())
                        # else:
                        #    setattr(prof, field, val)
                        prof.put()

        # return ProfileForm
        return self._copyProfileToForm(prof)

    def _getWishlist(self):
        """Get all wishlisted sessions for a user."""
        # get user Profile
        prof = self._getProfileFromUser()

        s_keys = [ndb.Key(urlsafe=wssk) for wssk in prof.wishlist]
        sessions = ndb.get_multi(s_keys)

        if not sessions:
             return SessionForm()
        else:
            # return SessionForms from user wishlist
            return SessionForms(
                sessions=[self._copySessionToForm(session) for session in sessions]
            )

    @endpoints.method(message_types.VoidMessage, ProfileForm,
            path='profile', http_method='GET', name='getProfile')
    def getProfile(self, request):
        """Return user profile."""
        return self._doProfile()


    @endpoints.method(ProfileMiniForm, ProfileForm,
            path='profile', http_method='POST', name='saveProfile')
    def saveProfile(self, request):
        """Update & return user profile."""
        return self._doProfile(request)


# - - - Announcements - - - - - - - - - - - - - - - - - - - -

    @staticmethod
    def _cacheAnnouncement():
        """Create Announcement & assign to memcache; used by
        memcache cron job & putAnnouncement().
        """
        confs = Conference.query(ndb.AND(
            Conference.seatsAvailable <= 5,
            Conference.seatsAvailable > 0)
        ).fetch(projection=[Conference.name])

        if confs:
            # If there are almost sold out conferences,
            # format announcement and set it in memcache
            announcement = ANNOUNCEMENT_TPL % (
                ', '.join(conf.name for conf in confs))
            memcache.set(MEMCACHE_ANNOUNCEMENTS_KEY, announcement)
        else:
            # If there are no sold out conferences,
            # delete the memcache announcements entry
            announcement = ""
            memcache.delete(MEMCACHE_ANNOUNCEMENTS_KEY)

        return announcement

    @staticmethod
    def _cacheFeaturedSpeaker(self):
        """
        Create memcache for a featured Speaker of a conference.
        """
        # Get the conference that the speaker is speaking
        # at from the websafeKey provided in the request
        conf_k = ndb.Key(urlsafe=self.request.get('key'))
        conf = conf_k.get()
        # The speaker that was just added
        addedSpeaker = self.request.get('speaker')
        # Find the speaker in the most sessions giving a Confenence
        # and return (name, sessionsCount)
        featuredSpeaker = Session.countspeakers(conf_k)
        speakerName = featuredSpeaker[0]
        sessionsSpeakersIn = featuredSpeaker[1]
        speakerMemKey = SPEAKER_ANNOUNCEMENTS_KEY + self.request.get('key')
        # Query that gets the name of the sessions the features speaker
        sessionsInfo = [session.name for session in \
            Session.query(ancestor=conf_k, projection=[Session.name]).\
            filter(Session.speaker == speakerName)]
        # Turn array into string then remove []
        if sessionsSpeakersIn > 1 and speakerName == addedSpeaker:
            speaker = {
                "name": speakerName.title(),
                "conf_name": conf.name.title(),
                "sessions": sessionsInfo
            }
            memcache.add(key=speakerMemKey, value=speaker, time=600)
        else:
            # If no feature speaker
            speaker = ""
            memcache.delete(speakerMemKey)
        return speaker

    @endpoints.method(message_types.VoidMessage, StringMessage,
            path='conference/announcement/get',
            http_method='GET', name='getAnnouncement')
    def getAnnouncement(self, request):
        """Return Announcement from memcache."""
        return StringMessage(data=memcache.get(MEMCACHE_ANNOUNCEMENTS_KEY) or "")


# - - - Registration - - - - - - - - - - - - - - - - - - - -

    @ndb.transactional(xg=True)
    def _conferenceRegistration(self, request, reg=True):
        """Register or unregister user for selected conference."""
        retval = None
        prof = self._getProfileFromUser() # get user Profile

        # check if conf exists given websafeConfKey
        # get conference; check that it exists
        wsck = request.websafeConferenceKey
        conf = ndb.Key(urlsafe=wsck).get()
        if not conf:
            raise endpoints.NotFoundException(
                'No conference found with key: %s' % wsck)

        # register
        if reg:
            # check if user already registered otherwise add
            if wsck in prof.conferenceKeysToAttend:
                raise ConflictException(
                    "You have already registered for this conference")

            # check if seats avail
            if conf.seatsAvailable <= 0:
                raise ConflictException(
                    "There are no seats available.")

            # register user, take away one seat
            prof.conferenceKeysToAttend.append(wsck)
            conf.seatsAvailable -= 1
            retval = True

        # unregister
        else:
            # check if user already registered
            if wsck in prof.conferenceKeysToAttend:

                # unregister user, add back one seat
                prof.conferenceKeysToAttend.remove(wsck)
                conf.seatsAvailable += 1
                retval = True
            else:
                retval = False

        # write things back to the datastore & return
        prof.put()
        conf.put()
        return BooleanMessage(data=retval)


    @endpoints.method(message_types.VoidMessage, ConferenceForms,
            path='conferences/attending',
            http_method='GET', name='getConferencesToAttend')
    def getConferencesToAttend(self, request):
        """Get list of conferences that user has registered for."""
        prof = self._getProfileFromUser() # get user Profile
        conf_keys = [ndb.Key(urlsafe=wsck) for wsck in prof.conferenceKeysToAttend]
        conferences = ndb.get_multi(conf_keys)

        # get organizers
        organisers = [ndb.Key(Profile, conf.organizerUserId) for conf in conferences]
        profiles = ndb.get_multi(organisers)

        # put display names in a dict for easier fetching
        names = {}
        for profile in profiles:
            names[profile.key.id()] = profile.displayName

        # return set of ConferenceForm objects per Conference
        return ConferenceForms(items=[self._copyConferenceToForm(conf, names[conf.organizerUserId])\
         for conf in conferences]
        )


    @endpoints.method(CONF_GET_REQUEST, BooleanMessage,
            path='conference/{websafeConferenceKey}',
            http_method='POST', name='registerForConference')
    def registerForConference(self, request):
        """Register user for selected conference."""
        return self._conferenceRegistration(request)


    @endpoints.method(CONF_GET_REQUEST, BooleanMessage,
            path='conference/{websafeConferenceKey}',
            http_method='DELETE', name='unregisterFromConference')
    def unregisterFromConference(self, request):
        """Unregister user for selected conference."""
        return self._conferenceRegistration(request, reg=False)


    @endpoints.method(message_types.VoidMessage, ConferenceForms,
            path='filterPlayground',
            http_method='GET', name='filterPlayground')
    def filterPlayground(self, request):
        """Filter Playground"""
        q = Conference.query()
        # field = "city"
        # operator = "="
        # value = "London"
        # f = ndb.query.FilterNode(field, operator, value)
        # q = q.filter(f)
        q = q.filter(Conference.city=="London")
        q = q.filter(Conference.topics=="Medical Innovations")
        q = q.filter(Conference.month==6)

        return ConferenceForms(
            items=[self._copyConferenceToForm(conf, "") for conf in q]
        )

# - - - Sessions - - - - - - - - - - - - - - - - - - - -

    def _copySessionToForm(self, session):
        """Copy relevant fields from Conference to ConferenceForm."""
        # copy relevant fields from Sesson to SessionForm
        sf = SessionForm()
        for field in sf.all_fields():
            if hasattr(session, field.name):
                # convert typeOfSession; just copy others
                if field.name == "typeOfSession":
                    setattr(sf, field.name, getattr(TypeOfSession, getattr(session, field.name)))
                else:
                    setattr(sf, field.name, getattr(session, field.name))
        sf.check_initialized()
        return sf

    def _sessionAdd(self, request):
        """Create a Session """
        prof = self._getProfileFromUser()  # get user Profile

        # check if conf exists given websafeConfKey
        # get conference; check that it exists
        wsck = request.websafeConferenceKey
        conf_k = ndb.Key(urlsafe=wsck)
        conf = conf_k.get()
        if not conf:
            raise endpoints.NotFoundException(
                'No conference found with key: %s' % wsck)

        if prof.mainEmail != conf.organizerUserId:
            raise endpoints.NotFoundException(
                'Cannont create a sessions from this conference')
        # Check for valid time
        if 24 < request.startTime or 0 >= request.startTime:
            raise endpoints.NotFoundException(
                'Invalid time, Please use 24 hour format. e.g 17')
        data = {field.name: getattr(request, field.name) for field in request.all_fields()}
        del data['websafeConferenceKey']

        if not data['typeOfSession']:
            data['typeOfSession'] = "NOT_SPECIFIED"
        else:
            data['typeOfSession'] = data['typeOfSession'].name
        # Allocates a range of key IDs for this model class.
        s_id = Session.allocate_ids(size=1, parent=conf_k)[0]
        # Create a Session key the includes session and parent info
        s_key = ndb.Key(Session, s_id, parent=conf_k)
        data['key'] = s_key
        session = Session(**data)
        s = session.put()
        # Added a task to check for feature speaker
        taskqueue.add(url='/tasks/set_Featured_Speaker',\
                      params={'key': wsck, 'speaker': data['speaker']})
        return self._copySessionToForm(s.get())

    @ndb.transactional(retries=2)
    def _wishlistAdd(self, request):
        """
        Let users wishlist session, and increase wishlist count each
        time a sessions is wishlisted
        """
        prof = self._getProfileFromUser()  # get user Profile
        s_key = request.websafeSessionsKey
        session = ndb.Key(urlsafe=s_key).get()
        if s_key in prof.wishlist:
            raise endpoints.NotFoundException(
                'Sessions is already on your wishlist')
        prof.wishlist.append(s_key)
        session.wishlisted += 1
        prof.put()
        session.put()
        return self._copyProfileToForm(prof)

    def _querySessions(self, filters, key=None):
        """
        Gernal query used for searching Sessions.
        """
        if key:
            # get Conference object from request; bail if not found
            safeKey = ndb.Key(urlsafe=key)
            conf = safeKey.get()
            if not conf:
                raise endpoints.NotFoundException(
                    'No conference found with key: %s' % key)
            q = Session.query(ancestor=safeKey)
        else:
            q = Session.query()

        if filters:
            inequality_filter, filters, excluded_values = self._formatMutliInequality(filters)
            # If exists, sort on inequality filter first
            if inequality_filter:
                q = q.order(ndb.GenericProperty(inequality_filter))

            q = q.order(Session.startTime)
            q = q.order(Session.name)

            for filtr in filters:
                formatted_query = ndb.query.FilterNode(filtr["field"], filtr["operator"], filtr["value"])
                q = q.filter(formatted_query)

            if excluded_values:
                """
                This code is used to solve query extra credit problem.
                Create list of session types but exclude the not equal to type
                """
                # Create list by turning TypeOfSession EMUN into dict then
                # filtered out values that are in the excluded_values list.
                typeOfSession = [typeOfSession for typeOfSession in \
                                 TypeOfSession.to_dict() if typeOfSession\
                                 not in excluded_values]
                FilterList = []
                # Add additional filter to query
                for i in typeOfSession:
                    FilterList.append(ndb.query.FilterNode('typeOfSession', '=', i))

                q = q.filter(ndb.OR(*FilterList))

        return q

    def _formatMutliInequality(self, filters):
        """Parse, check validity and format user supplied filters."""
        formatted_filters = []
        excluded_values = []
        inequality_field = None
        for f in filters:
            filtr = {field.name: getattr(f, field.name) for field in f.all_fields()}
            # Converting START_TIME to int
            if filtr["field"] == "START_TIME":
                filtr["value"] = int(filtr["value"])
            # Checking to see if all field are valid.
            try:
                filtr["field"] = FIELDS[filtr["field"]]
                filtr["operator"] = OPERATORS[filtr["operator"]]
            except KeyError:
                raise endpoints.BadRequestException("Filter contains invalid\
                field or operator.")

            # Every operation except "=" is an inequality
            if filtr["operator"] != "=":
                """
                Remove session type inequality part of my solution for solving
                the query problem asked for extra credit, also only allow not
                equal inequality for operator because checking for types less
                then 'WORKSHOP' makes no sense.
                """
                if filtr["field"] == "typeOfSession":
                    # Only add the not equal operator.
                    if filtr["operator"] != "!=":
                        raise endpoints.BadRequestException("Can only one \
                            exclude values ")
                    # Add all good values to list.
                    excluded_values.append(filtr["value"].upper())
                    continue
                if inequality_field and inequality_field != filtr["field"]:
                    raise endpoints.BadRequestException("Inequality filter is\
                    allowed on only one field.")
                else:
                    inequality_field = filtr["field"]

            formatted_filters.append(filtr)
        return (inequality_field, formatted_filters, excluded_values)

    @endpoints.method(CONF_GET_REQUEST, SessionForms,
            path='conference/{websafeConferenceKey}/sessions',
            http_method='GET', name='getConferenceSessions')
    def getConferenceSessions(self, request):
        """
        Return requested sessions for a conference (by websafeConferenceKey).
        """
        # get Conference object from request; bail if not found
        conf_k = ndb.Key(urlsafe=request.websafeConferenceKey)
        conf = conf_k.get()
        if not conf:
            raise endpoints.NotFoundException(
                'No conference found with key: %s' % request.websafeConferenceKey)

        sessions = Session.query(ancestor=conf_k)

        # return ConferenceForm
        return SessionForms(sessions=[self._copySessionToForm(sess)\
                            for sess in sessions])

    @endpoints.method(message_types.VoidMessage, SessionForms,
        path='getMostWishlisted',
        http_method='GET', name='getMostWishlisted')
    def getMostWishlisted(self, request):
        """
        One of the additional queries.
        See which sessions Users are most excited about, by getting
        the top 10 most wishlisted sessions.
        """
        sessions = Session.query(Session.wishlisted > 0 ).order(-Session.wishlisted).fetch(10)
        return SessionForms(sessions=[self._copySessionToForm(sess)\
                            for sess in sessions])

    @endpoints.method(SINGLE_POST_REQUEST, SessionForms,
        path='conference/{websafeConferenceKey}/getSessionsPerDay',
        http_method='POST', name='getSessionsPerDay')
    def getSessionsPerDay(self, request):
        """
        Second of the additional queries.
        Get all conference sessions during a day
        """
        key = ndb.Key(urlsafe=request.websafeConferenceKey)
        conf = key.get()
        if not conf:
            raise endpoints.NotFoundException(
                'No conference found with key: %s' % key)
        # Check is values are valid
        if request.field != "DAY" or request.operator not in OPERATORS:
            raise endpoints.NotFoundException('Can only filter by day or\
             check operator')
        # Make sure value is number
        try:
            int(request.value)
        except:
            raise endpoints.NotFoundException('Please use a number')
        sessions = Session.query(ancestor=key).\
            filter(ndb.query.FilterNode(FIELDS[request.field],\
            OPERATORS[request.operator], int(request.value))).\
            order(Session.startTime)
        return SessionForms(sessions=[self._copySessionToForm(sess)\
                            for sess in sessions])

    @endpoints.method(SINGLE_POST_REQUEST, SessionForms,
        path='conference/{websafeConferenceKey}/sessionsByType',
        http_method='POST', name='getConferenceSessionsByType')
    def getConferenceSessionsByType(self, request):
        """
        Given a conference, return all sessions of a specified type
        (eg lecture, keynote, workshop)
        """
        key = ndb.Key(urlsafe=request.websafeConferenceKey)
        conf = key.get()
        value = request.value.upper()
        if not conf:
            raise endpoints.NotFoundException(
                'No conference found with key: %s' % key)
        # Check if field and operation are valid
        if request.field != "TYPE" or request.operator not in OPERATORS:
            raise endpoints.NotFoundException('Can only filter by type or check operator')
        # Check if value is valid
        if value not in TypeOfSession.to_dict():
            raise endpoints.NotFoundException('Not a valid session type')
        sessions = Session.query(ancestor=key).\
            filter(ndb.query.FilterNode(FIELDS[request.field],\
            OPERATORS[request.operator], value)).\
            order(Session.startTime)
        return SessionForms(sessions=[self._copySessionToForm(sess)\
                            for sess in sessions])

    @endpoints.method(SpeakerSessionQueryForm, SessionForms,
        path='speakers',
        http_method='POST', name='getSessionsBySpeakers')
    def getSessionsBySpeakers(self, request):
        """
        Given a speaker, return all sessions given by this particular
        speaker, acroos all conferences.
        """
        sessions = Session.query(Session.speaker == request.speaker.lower())
        return SessionForms(sessions=[self._copySessionToForm(sess)\
                            for sess in sessions])

    @endpoints.method(QUERY_POST_REQUEST, SessionForms,
        path='conference/{websafeConferenceKey}/sessions',
        http_method='POST', name='getQuerySessions')
    def getQuerySessions(self, request):
        """
        Query all sessions in a conference, use for credit extra problem.
        """
        sessions = self._querySessions(request.filters, request.websafeConferenceKey)
        return SessionForms(sessions=[self._copySessionToForm(sess)\
                            for sess in sessions])

    @endpoints.method(SESS_POST_REQUEST, SessionForm,
            path='conference/{websafeConferenceKey}/session',
            http_method='POST', name='createSession')
    def createSession(self, request):
        """Creat a session for a conference."""
        return self._sessionAdd(request)

    @endpoints.method(WISHLIST_POST_REQUEST, ProfileForm,
            path='session/{websafeSessionsKey}/addSessionToWishlist',
            http_method='POST', name='addSessionToWishlist')
    def addSessionToWishlist(self, request):
        """
        Adds the sessions to the user's list of
        sessions the are interested in attending.
        """
        return self._wishlistAdd(request)

    @endpoints.method(message_types.VoidMessage, SessionForms,
            path='profile/wishlist', http_method='GET',
            name='getSessionsInWishlist')
    def getSessionsInWishlist(self, request):
        """Get all sessions on user wishlist."""
        return self._getWishlist()

    @endpoints.method(CONF_GET_REQUEST, FeatureSpeaker,
            path='conference/{websafeConferenceKey}/getFeatureSpeaker',
            http_method='GET', name='getFeatureSpeaker')
    def getFeatureSpeaker(self, request):
        """
        Return the featrue speaker for a conference and all sessions the
        feature speaker is in.
        """
        speakerMemKey = SPEAKER_ANNOUNCEMENTS_KEY + request.websafeConferenceKey
        data = memcache.get(speakerMemKey)
        if data is not None:
            return FeatureSpeaker(
                name= data['name'],
                conf_name= data['conf_name'],
                sessions= data['sessions']
            )
        else:
            raise endpoints.NotFoundException('Not a valid Memcache id')

api = endpoints.api_server([ConferenceApi])  # register API
