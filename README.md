## Udacity Project 4 Overview
Develop a cloud-based API server to support a provided conference organization application that exists on the web. The 
API supports the following functionality found within the app: user authentication, user profiles, conference information and
various manners in which to query the data.

Site is [live](https://project-four.appspot.com/)

## Products
- [App Engine][1]

## Language
- [Python][2]

## APIs
- [Google Cloud Endpoints][3]

## Setup Instructions
1. Update the value of `application` in `app.yaml` to the app ID you
   have registered in the App Engine admin console and would like to use to host
   your instance of this sample.
1. Update the values at the top of `settings.py` to
   reflect the respective client IDs you have registered in the
   [Developer Console][4].
1. Update the value of CLIENT_ID in `static/js/app.js` to the Web client ID
1. (Optional) Mark the configuration files as unchanged as follows:
   `$ git update-index --assume-unchanged app.yaml settings.py static/js/app.js`
1. Run the app with the devserver using `dev_appserver.py DIR`, and ensure it's running by visiting your local server's address (by default [localhost:8080][5].)
1. (Optional) Generate your client library(ies) with [the endpoints tool][6].
1. Deploy your application.


## Design Choice 
```
"""Session -- Session object"""
name            = ndb.StringProperty(required=True)
highlights      = ndb.StringProperty()
speaker         = ndb.StringProperty()
duration        = ndb.IntegerProperty()
typeOfSession   = ndb.StringProperty(default='NOT_SPECIFIED')
dayofConf       = ndb.IntegerProperty(default=1)
startTime       = ndb.IntegerProperty()
wishlisted      = ndb.IntegerProperty(default=0) 
```
Choose to make the type of sessions (typeOfSession) an Emun you help solve the extra credit problem,
see the Query solution exampled for more information. Added a day of conference (dayofConf), to easily
search and see that is happening during certain day of a conference. Wish-list counter(wishlisted) was
added to track how popular a session is, sense users can only wishlist a session once this a good way
to see how my different users want to attend a session. 

Decided against making the speaker it own entity because as more conference are created user can reused
speakers. If a conference creator when to tailor the speakers info to suit their conference needs,
this would change the speaker's info across all conferences and this may no be o the liking
of everybody. You could restrict edits to conference that include that speaker but to me that
the same as having it all in under session entity. 

## Query solution exampled:
Query asked:
```
q = Session.all()
q.filter("typeOfSession !=", "WORKSHOPS")
q.filter("height >", 19)
```
Datastore only allows you to use an inequality filter on one property. So my workaround for this issue was
to get a list of all session types, then exact "WORKSHOPS" from the list. With that list I used an OR filter
on each item.
`q.filter(ndb.OR(ndb.query.FilterNode('typeOfSession', '=', listItem))`
The problem with this approach is that depending on how many different sessions type there, your query could
exploded quickly. To limit this a issue I restricted the accepted session types. If users feel they need more
types the list can be easily extended.   
   
## Additional Queries
####Query One getMostWishlisted():
This shows the top 10 wish-listed sessions. This useful because user can what is sessions are trending 
####Query Two getSessionsPerDay(websafeConferenceKey):
Shows all sessions based on the day of a conference. This is helpful if use only want to day you are attending or if a day has passed users can only the remaining days. 

[1]: https://developers.google.com/appengine
[2]: http://python.org
[3]: https://developers.google.com/appengine/docs/python/endpoints/
[4]: https://console.developers.google.com/
[5]: https://localhost:8080/
[6]: https://developers.google.com/appengine/docs/python/endpoints/endpoints_tool
