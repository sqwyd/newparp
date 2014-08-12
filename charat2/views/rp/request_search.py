import datetime

from flask import abort, g, jsonify, redirect, render_template, request, url_for
from sqlalchemy import and_, func
from sqlalchemy.orm import joinedload, joinedload_all
from sqlalchemy.orm.exc import NoResultFound
from uuid import uuid4
from webhelpers import paginate

from charat2.helpers import alt_formats
from charat2.helpers.auth import login_required
from charat2.model import (
    ChatUser,
    Message,
    Request,
    RequestTag,
    SearchedChat,
    Tag,
    UserCharacter,
)
from charat2.model.connections import use_db


def _own_request_query(request_id):
    try:
        search_request = g.db.query(Request).filter(Request.id == request_id).one()
    except NoResultFound:
        abort(404)
    if search_request.user != g.user:
        abort(404)
    return search_request


def _tags_from_form(form):
    request_tags = []
    for tag_type in Tag.type_options:
        names = {}
        for alias in form[tag_type].split(","):
            alias = alias.strip()
            if alias == "":
                continue
            name = alias.lower().replace(" ", "_")[:50]
            names[name] = alias
        for name, alias in names.iteritems():
            try:
                tag = g.db.query(Tag).filter(and_(
                    Tag.type == tag_type, Tag.name == name,
                )).one()
            except:
                tag = Tag(type=tag_type, name=name)
            request_tags.append(RequestTag(tag=tag, alias=alias))
    return request_tags


@alt_formats(set(["json"]))
@use_db
@login_required
def request_list(fmt=None, page=1):

    requests = g.db.query(Request).order_by(
        Request.posted.desc(),
    ).filter(
        Request.status == "posted",
    ).options(
        joinedload_all("tags.tag")
    ).offset((page-1)*50).limit(50).all()

    if len(requests) == 0 and page != 1:
        abort(404)

    request_count = g.db.query(func.count('*')).select_from(Request).filter(
        Request.status == "posted",
    ).scalar()

    if fmt == "json":
        return jsonify({
            "total": request_count,
            "requests": [_.to_dict(user=g.user) for _ in requests],
        })

    paginator = paginate.Page(
        [],
        page=page,
        items_per_page=50,
        item_count=request_count,
        url=lambda page: url_for("rp_request_list", page=page),
    )

    return render_template(
        "rp/request_search/request_list.html",
        page="all",
        requests=requests,
        paginator=paginator,
    )


@alt_formats(set(["json"]))
@use_db
@login_required
def your_request_list(fmt=None, page=1):

    requests = g.db.query(Request).order_by(
        Request.posted.desc(),
    ).filter(
        Request.user_id == g.user.id,
    ).offset((page-1)*50).limit(50).all()

    if len(requests) == 0 and page != 1:
        abort(404)

    request_count = g.db.query(func.count('*')).select_from(Request).filter(
        Request.user_id == g.user.id,
    ).scalar()

    if fmt == "json":
        return jsonify({
            "total": request_count,
            "requests": [_.to_dict(user=g.user) for _ in requests],
        })

    paginator = paginate.Page(
        [],
        page=page,
        items_per_page=50,
        item_count=request_count,
        url=lambda page: url_for("rp_your_request_list", page=page),
    )

    return render_template(
        "rp/request_search/request_list.html",
        page="yours",
        requests=requests,
        paginator=paginator,
    )


def _new_request_form(error=None):

    characters = g.db.query(UserCharacter).filter(
        UserCharacter.user_id == g.user.id,
    ).order_by(UserCharacter.title, UserCharacter.id).all()

    selected_character = None
    if "character_id" in request.form:
        try:
            selected_character = int(request.form["character_id"])
        except ValueError:
            pass

    return render_template(
        "rp/request_search/new_request.html",
        characters=characters,
        selected_character=selected_character,
        error=error,
    )


@use_db
@login_required
def new_request_get():
    return _new_request_form()


@use_db
@login_required
def new_request_post():

    scenario = request.form["scenario"].strip()
    prompt = request.form["prompt"].strip()

    # At least one of prompt or scenario must be filled in.
    if len(scenario) == 0 and len(prompt) == 0:
        return _new_request_form(error="blank")

    # Just make the character none if the specified character isn't valid.
    try:
        character = g.db.query(UserCharacter).filter(and_(
            UserCharacter.id == int(request.form["character_id"]),
            UserCharacter.user_id == g.user.id,
        )).one()
    except (KeyError, ValueError, NoResultFound):
        character = None

    new_request = Request(
        user=g.user,
        status="draft" if "draft" in request.form else "posted",
        user_character=character,
        scenario=scenario,
        prompt=prompt,
    )

    new_request.tags = _tags_from_form(request.form)

    g.db.add(new_request)

    return redirect(url_for("rp_your_request_list"))


@use_db
@login_required
def answer_request(request_id):

    try:
        search_request = g.db.query(Request).filter(
            Request.id == request_id,
        ).options(
            joinedload(Request.user),
            joinedload(Request.user_character),
        ).one()
    except NoResultFound:
        abort(404)

    if search_request.status != "posted" or search_request.user == g.user:
        abort(404)

    new_chat = SearchedChat(url=str(uuid4()).replace("-", ""))
    g.db.add(new_chat)
    g.db.flush()

    if search_request.user_character is not None:
        new_chat_user = ChatUser.from_character(
            search_request.user_character,
            chat_id=new_chat.id,
        )
    else:
        new_chat_user = ChatUser.from_user(
            search_request.user,
            chat_id=new_chat.id,
        )
    g.db.add(new_chat_user)

    if len(search_request.scenario) > 0:
        g.db.add(Message(
            chat_id=new_chat.id,
            type="search_info",
            acronym="Scenario",
            text=search_request.scenario,
        ))

    if len(search_request.prompt) > 0:
        g.db.add(Message(
            chat_id=new_chat.id,
            user_id=new_chat_user.user_id,
            type="ic",
            color=new_chat_user.color,
            acronym=new_chat_user.acronym,
            name=new_chat_user.name,
            text=search_request.prompt,
        ))

    return redirect(url_for("chat", url=new_chat.url))


def _edit_request_form(search_request, error=None):

    characters = g.db.query(UserCharacter).filter(
        UserCharacter.user_id == g.user.id,
    ).order_by(UserCharacter.title, UserCharacter.id).all()

    selected_character = None
    if "character_id" in request.form:
        try:
            selected_character = int(request.form["character_id"])
        except ValueError:
            pass

    return render_template(
        "rp/request_search/edit_request.html",
        search_request=search_request,
        characters=characters,
        selected_character=selected_character,
        error=error,
    )


@use_db
@login_required
def edit_request_get(request_id):
    return _edit_request_form(_own_request_query(request_id))


@use_db
@login_required
def edit_request_post(request_id):

    search_request = _own_request_query(request_id)

    scenario = request.form["scenario"].strip()
    prompt = request.form["prompt"].strip()

    # At least one of prompt or scenario must be filled in.
    if len(scenario) == 0 and len(prompt) == 0:
        return _edit_request_form(search_request, error="blank")

    # Just make the character none if the specified character isn't valid.
    try:
        character = g.db.query(UserCharacter).filter(and_(
            UserCharacter.id == int(request.form["character_id"]),
            UserCharacter.user_id == g.user.id,
        )).one()
    except (KeyError, ValueError, NoResultFound):
        character = None

    search_request.scenario = scenario
    search_request.prompt = prompt
    search_request.user_character = character

    if "draft" in request.form:
        search_request.status = "draft"
    elif search_request.status != "posted":
        search_request.status = "posted"
        # Bump the date if the request is being re-posted.
        search_request.posted = datetime.datetime.now()

    return redirect(url_for("rp_edit_request_get", request_id=search_request.id))


@use_db
@login_required
def delete_request_get(request_id):
    return render_template(
        "rp/request_search/delete_request.html",
        search_request=_own_request_query(request_id),
    )


@use_db
@login_required
def delete_request_post(request_id):
    search_request = _own_request_query(request_id)
    g.db.delete(search_request)
    g.db.commit()
    return redirect(url_for("rp_your_request_list"))
