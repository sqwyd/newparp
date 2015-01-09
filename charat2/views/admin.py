from flask import abort, g, jsonify, redirect, render_template, request, url_for
from sqlalchemy import func
from sqlalchemy.orm import joinedload
from sqlalchemy.orm.exc import NoResultFound

from charat2.helpers import alt_formats
from charat2.helpers.auth import admin_required
from charat2.model import SearchCharacter, SearchCharacterChoice, User
from charat2.model.connections import use_db


@use_db
@admin_required
def announcements_get():
    return render_template("admin/announcements.html")


@use_db
@admin_required
def announcements_post():
    g.redis.set("announcements", request.form["announcements"])
    return redirect(url_for("admin_announcements"))


@alt_formats(set(["json"]))
@use_db
@admin_required
def user(username, fmt=None):
    try:
        user = (
            g.db.query(User).filter(func.lower(User.username) == username.lower())
            .options(
                joinedload(User.default_character),
                joinedload(User.search_character),
            ).one()
        )
    except NoResultFound:
        abort(404)
    # Redirect to fix capitalisation.
    if username != user.username:
        return redirect(url_for("admin_user", username=user.username))
    if fmt == "json":
        return jsonify(user.to_dict(include_options=True))
    search_characters = ", ".join(_.title for _ in (
        g.db.query(SearchCharacter)
        .select_from(SearchCharacterChoice)
        .join(SearchCharacter)
        .filter(SearchCharacterChoice.user_id == user.id)
        .order_by(SearchCharacter.name).all()
    ))
    return render_template("admin/user.html", User=User, user=user, search_characters=search_characters)


@use_db
@admin_required
def user_set_group(username):
    try:
        user = g.db.query(User).filter(func.lower(User.username) == username.lower()).one()
    except NoResultFound:
        abort(404)
    if request.form["group"] in User.group.type.enums:
        user.group = request.form["group"]
    else:
        abort(400)
    return redirect(url_for("admin_user", username=user.username))
