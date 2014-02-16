#!/usr/bin/python

import time

from redis import StrictRedis
from sqlalchemy import and_
from sqlalchemy.orm.exc import NoResultFound

from charat2.helpers.chat import disconnect, send_message
from charat2.model import sm, Message, UserChat
from charat2.model.connections import redis_pool

db = sm()
redis = StrictRedis(connection_pool=redis_pool)

if __name__ == "__main__":
    while True:
        current_time = int(time.time())
        for dead in redis.zrangebyscore("chats_alive", 0, current_time):
            chat_id, user_id = dead.split('/')
            disconnected = disconnect(redis, chat_id, user_id)
            # Only send a timeout message if they were already online.
            if not disconnected:
                continue
            try:
                dead_user_chat = db.query(UserChat).filter(and_(
                    UserChat.user_id==user_id,
                    UserChat.chat_id==chat_id,
                )).one()
            except NoResultFound:
                pass
            send_message(db, redis, Message(
                chat_id=chat_id,
                type="timeout",
                # omg i've been waiting so long to get rid of that FUCKING
                # SEMI COLON
                text="%s's connection timed out. Please don't quit straight "
                     "away, they could be back." % dead_user_chat.name,
            ))
            print current_time, "Reaping ", dead
        db.commit()
        time.sleep(1)

