## Udacity Project 4 Overview
You will develop a cloud-based API server to support a provided 
conference organization application that exists on the web. The 
API supports the following functionality found within the app: 
user authentication, user profiles, conference information and
various manners in which to query the data.

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
name            = ndb.StringProperty(required=True)
highlights      = ndb.StringProperty()
speaker         = ndb.StringProperty()
duration        = ndb.IntegerProperty()
typeOfSession   = ndb.StringProperty(default='NOT_SPECIFIED')
dayofConf       = ndb.IntegerProperty()
startTime       = ndb.IntegerProperty()
wishlisted      = ndb.IntegerProperty(default=0) 
```

Choice to make type of session an Emun you help solve and query issue that might arise. See the Query problem solution exampled
for more infomation. Added a day of confence(dayofConf) to seesion becaues if people wanna see that is happening during a certnet day of the confence.

Decide agsiant making the speaker it own enity because as more confernce are created user might want to reused speakers.
When a confence creator when to tailor the speakers info to suit their confence needs, this would change the info speaker info
accoss all confences and this may no be o the liking of everybody. Thought about restrictions edit but to me that the same as 
having it only in one enity. 
 

excluded a belong to field because that include with parent field

## Query problem solution exampled:
Query was:
```
q = Session.all()
q.filter("typeOfSession !=", "WORKSHOPS")
q.filter("height >", 19)
```
Datastore only allows you to use inequality filter on one property. So my workaround for this issue was
to get a list of all session types, then exact "WORKSHOPS" from the list. With that list I used an OR filter
on each item.
`q.filter(ndb.OR(ndb.query.FilterNode('typeOfSession', '=', listItem))`
The problem with this appoach is that depending on how many diffent sessions type there, your query
could be exploded quickly. To limit this a issue I limited the accpeted session types. If users feel they need more
types the list can be easily extended.   
   

[1]: https://developers.google.com/appengine
[2]: http://python.org
[3]: https://developers.google.com/appengine/docs/python/endpoints/
[4]: https://console.developers.google.com/
[5]: https://localhost:8080/
[6]: https://developers.google.com/appengine/docs/python/endpoints/endpoints_tool
