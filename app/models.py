from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from app import db

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    is_admin = db.Column(db.Boolean, default=False)
    
    # Single relationship definitions with overlaps parameter
    polls = db.relationship('Poll', 
                          backref=db.backref('author', overlaps="poll_author,created_polls"),
                          lazy='dynamic',
                          overlaps="created_polls,poll_author")
    
    comments = db.relationship('Comment', 
                             backref=db.backref('author', overlaps="comment_author,authored_comments"),
                             lazy='dynamic',
                             overlaps="authored_comments,comment_author")
    
    # Additional relationships with overlaps
    created_polls = db.relationship('Poll', 
                                  backref=db.backref('poll_author', overlaps="author"),
                                  lazy='dynamic',
                                  overlaps="polls,author")
    
    authored_comments = db.relationship('Comment', 
                                      backref=db.backref('comment_author', overlaps="author"),
                                      lazy='dynamic',
                                      overlaps="comments,author")

    # Privacy settings
    is_private = db.Column(db.Boolean, default=True)
    
    # Follow relationships
    followers = db.relationship('Follow',
                              foreign_keys='Follow.followed_id',
                              backref=db.backref('followed', lazy='joined'),
                              lazy='dynamic',
                              cascade='all, delete-orphan')
    following = db.relationship('Follow',
                              foreign_keys='Follow.follower_id',
                              backref=db.backref('follower', lazy='joined'),
                              lazy='dynamic',
                              cascade='all, delete-orphan')
    
    # Follow request relationships
    follow_requests_received = db.relationship('FollowRequest',
                                             foreign_keys='FollowRequest.requested_id',
                                             backref=db.backref('requested', lazy='joined'),
                                             lazy='dynamic',
                                             cascade='all, delete-orphan')
    follow_requests_sent = db.relationship('FollowRequest',
                                         foreign_keys='FollowRequest.requester_id',
                                         backref=db.backref('requester', lazy='joined'),
                                         lazy='dynamic',
                                         cascade='all, delete-orphan')

    # Add profile relationship
    profile = db.relationship('Profile', backref='user', uselist=False)

    # New field for pinned communities
    pinned_communities = db.relationship('Community', 
                                       secondary='pinned_communities',
                                       backref=db.backref('pinned_by', lazy='dynamic'))

    # New field for pinned conversations
    pinned_conversations = db.relationship('User',
        secondary='pinned_conversations',
        primaryjoin='PinnedConversations.user_id == User.id',
        secondaryjoin='PinnedConversations.conversation_with_id == User.id',
        backref=db.backref('pinned_by', lazy='dynamic'),
        lazy='dynamic'
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
        
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def follow(self, user):
        if not self.is_following(user):
            f = Follow(follower=self, followed=user)
            db.session.add(f)
            db.session.commit()

    def unfollow(self, user):
        f = self.following.filter_by(followed_id=user.id).first()
        if f:
            db.session.delete(f)
            db.session.commit()

    def is_following(self, user):
        return self.following.filter_by(followed_id=user.id).first() is not None

    def send_follow_request(self, user):
        if not self.has_follow_request_pending(user):
            fr = FollowRequest(requester=self, requested=user)
            db.session.add(fr)

    def has_follow_request_pending(self, user):
        return self.follow_requests_sent.filter_by(requested_id=user.id).first() is not None

    def accept_follow_request(self, user):
        fr = self.follow_requests_received.filter_by(requester_id=user.id).first()
        if fr:
            try:
                # Create the follow relationship
                f = Follow(follower=user, followed=self)
                db.session.add(f)
                # Delete the follow request
                db.session.delete(fr)
                # Commit both changes
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                raise e

    def reject_follow_request(self, user):
        fr = self.follow_requests_received.filter_by(requester_id=user.id).first()
        if fr:
            db.session.delete(fr)

    def can_dm(self, user):
        """Check if users can DM each other (mutual followers)"""
        return self.is_following(user) and user.is_following(self)

    def get_dm_history(self, other_user):
        """Get DM history between two users"""
        return DirectMessage.query.filter(
            ((DirectMessage.sender_id == self.id) & (DirectMessage.recipient_id == other_user.id)) |
            ((DirectMessage.sender_id == other_user.id) & (DirectMessage.recipient_id == self.id))
        ).order_by(DirectMessage.created_at.desc()).all()

class University(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    country = db.Column(db.String(100))
    domain = db.Column(db.String(100))
    programs = db.relationship('Program', backref='university', lazy=True)

class Program(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    university_id = db.Column(db.Integer, db.ForeignKey('university.id'), nullable=False)

class Poll(db.Model):
    DEFAULT_OPTION = "Just viewing results 🍿"
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    end_date = db.Column(db.DateTime)
    poll_type = db.Column(db.String(50))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    # Add upvotes relationship
    upvotes = db.relationship('PollVote', backref='poll', lazy='dynamic', cascade='all, delete-orphan')
    
    # These relationships are defined in User class
    options = db.relationship('PollOption', backref='poll', lazy='dynamic', cascade='all, delete-orphan')
    comments = db.relationship('Comment', backref='poll', lazy='dynamic', cascade='all, delete-orphan')

    @property
    def upvote_count(self):
        return self.upvotes.count()

    def is_upvoted_by(self, user):
        if not user or user.is_anonymous:
            return False
        return PollVote.query.filter_by(
            user_id=user.id,
            poll_id=self.id
        ).first() is not None

    def toggle_upvote(self, user):
        if not user or user.is_anonymous:
            return False
        
        vote = PollVote.query.filter_by(
            user_id=user.id,
            poll_id=self.id
        ).first()
        
        if vote:
            db.session.delete(vote)
            return 'removed'
        else:
            vote = PollVote(user_id=user.id, poll_id=self.id)
            db.session.add(vote)
            return 'added'

    def total_votes(self):
        try:
            return sum(option.votes.count() for option in self.options)
        except Exception as e:
            print(f"Error calculating total votes: {e}")
            return 0
    
    def has_user_voted(self, user):
        if not user or user.is_anonymous:
            return False
        try:
            return any(vote.user_id == user.id for option in self.options for vote in option.votes)
        except Exception as e:
            print(f"Error checking if user voted: {e}")
            return False

    def get_user_vote(self, user):
        if not user or user.is_anonymous:
            return None
        try:
            for option in self.options:
                vote = Vote.query.filter_by(user_id=user.id, option_id=option.id).first()
                if vote:
                    return option
            return None
        except Exception as e:
            print(f"Error getting user vote: {e}")
            return None

    def is_active(self):
        if not self.end_date:
            return True
        return self.end_date > datetime.utcnow()

    def __repr__(self):
        return f'<Poll {self.id}: {self.title}>'

class PollOption(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.String(200), nullable=False)
    poll_id = db.Column(db.Integer, db.ForeignKey('poll.id'))
    votes = db.relationship('Vote', backref='option', lazy='dynamic')

class Vote(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    option_id = db.Column(db.Integer, db.ForeignKey('poll_option.id'))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    poll_id = db.Column(db.Integer, db.ForeignKey('poll.id'), nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey('comment.id'))
    
    # These relationships are defined in User class
    replies = db.relationship(
        'Comment',
        backref=db.backref('parent', remote_side=[id]),
        lazy='dynamic',
        cascade='all, delete-orphan'
    )

    def __repr__(self):
        return f'<Comment {self.id}>'

class AdmissionResult(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    university = db.Column(db.String(200), nullable=False)
    program = db.Column(db.String(200), nullable=False)
    decision = db.Column(db.String(50), nullable=False)  # Accepted, Rejected, Waitlisted
    degree_type = db.Column(db.String(50), nullable=False)  # PhD, Masters, etc.
    term = db.Column(db.String(50), nullable=False)  # Fall 2024, Spring 2025, etc.
    notification_date = db.Column(db.DateTime, nullable=False)
    gpa = db.Column(db.Float, nullable=True)
    gre_verbal = db.Column(db.Integer, nullable=True)
    gre_quant = db.Column(db.Integer, nullable=True)
    gre_awa = db.Column(db.Float, nullable=True)
    comments = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

poll_tags = db.Table('poll_tags',
    db.Column('poll_id', db.Integer, db.ForeignKey('poll.id')),
    db.Column('tag_id', db.Integer, db.ForeignKey('tag.id'))
)

class Tag(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True)
    polls = db.relationship('Poll', secondary=poll_tags, backref='tags')

class UserSettings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    email_notifications = db.Column(db.Boolean, default=True)
    default_poll_visibility = db.Column(db.String(20), default='public')
    theme = db.Column(db.String(20), default='light') 

class Profile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), unique=True)
    
    # Undergraduate Details
    university = db.Column(db.String(100))
    major = db.Column(db.String(100))
    gpa = db.Column(db.Float)
    gpa_scale = db.Column(db.Float, default=4.0)
    
    # Test Scores
    toefl_score = db.Column(db.Integer)
    ielts_score = db.Column(db.Float)
    gre_verbal = db.Column(db.Integer)
    gre_quant = db.Column(db.Integer)
    gre_awa = db.Column(db.Float)
    
    # Work Experience
    work_experience_years = db.Column(db.Float)
    current_job = db.Column(db.String(100))
    company = db.Column(db.String(100))
    
    # Research Experience
    research_experience = db.Column(db.Boolean, default=False)
    publications = db.Column(db.Integer, default=0)
    
    # Additional Information
    target_term = db.Column(db.String(20))  # e.g., "Fall 2024"
    target_degree = db.Column(db.String(20))  # e.g., "MS", "PhD"
    target_major = db.Column(db.String(100))
    
    # Bio/About
    bio = db.Column(db.Text)

    def __repr__(self):
        return f'<Profile of {self.user.username}>'

class Application(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    university = db.Column(db.String(200), nullable=False)
    program = db.Column(db.String(200), nullable=False)
    term = db.Column(db.String(50), nullable=False)  # e.g., "Fall 2024"
    degree_type = db.Column(db.String(50), nullable=False)  # e.g., "MS", "PhD"
    
    # Application Status and Dates
    status = db.Column(db.String(50), default='Planning')  # Planning, Applied, Interview, Accepted, Rejected, Waitlisted
    applied_date = db.Column(db.DateTime)
    decision_date = db.Column(db.DateTime)
    
    # Application Details
    application_fee = db.Column(db.Float)
    fee_paid = db.Column(db.Boolean, default=False)
    
    # Documents
    transcripts_submitted = db.Column(db.Boolean, default=False)
    lors_submitted = db.Column(db.Integer, default=0)  # Number of LORs submitted
    sop_submitted = db.Column(db.Boolean, default=False)
    resume_submitted = db.Column(db.Boolean, default=False)
    
    # Additional Info
    deadline = db.Column(db.DateTime)
    notes = db.Column(db.Text)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    user = db.relationship('User', backref='applications')

# New models for follow functionality
class Follow(db.Model):
    __tablename__ = 'follows'
    follower_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), primary_key=True)
    followed_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        db.UniqueConstraint('follower_id', 'followed_id', name='unique_follow_constraint'),
    )

class FollowRequest(db.Model):
    __tablename__ = 'follow_requests'
    requester_id = db.Column(db.Integer, db.ForeignKey('user.id'), primary_key=True)
    requested_id = db.Column(db.Integer, db.ForeignKey('user.id'), primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class PollVote(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    poll_id = db.Column(db.Integer, db.ForeignKey('poll.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Ensure a user can only upvote a poll once
    __table_args__ = (db.UniqueConstraint('user_id', 'poll_id'),)

def create_admin():
    admin = User(
        username='admin',
        email='admin@example.com',
        is_admin=True
    )
    admin.set_password('1234')
    db.session.add(admin)
    db.session.commit()

class Community(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    university = db.Column(db.String(100), nullable=False)
    program = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    
    # Ensure no duplicate communities for same university/program combination
    __table_args__ = (
        db.UniqueConstraint('university', 'program', name='unique_university_program'),
    )
    
    # Relationships
    members = db.relationship('User', secondary='community_members')
    messages = db.relationship('CommunityMessage', backref='community', lazy='dynamic')
    created_by = db.relationship('User', backref='communities_created')

class CommunityMembers(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    community_id = db.Column(db.Integer, db.ForeignKey('community.id'))
    joined_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        db.UniqueConstraint('user_id', 'community_id', name='unique_community_member'),
    )

class CommunityMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    community_id = db.Column(db.Integer, db.ForeignKey('community.id'))
    
    # Relationship
    author = db.relationship('User', backref='community_messages')

class PinnedCommunities(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    community_id = db.Column(db.Integer, db.ForeignKey('community.id'))
    pinned_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        db.UniqueConstraint('user_id', 'community_id', name='unique_pinned_community'),
    )

class DirectMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    recipient_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    read = db.Column(db.Boolean, default=False)
    pinned = db.Column(db.Boolean, default=False)
    
    sender = db.relationship('User', foreign_keys=[sender_id])
    recipient = db.relationship('User', foreign_keys=[recipient_id])

class PinnedConversations(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    conversation_with_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    pinned_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        db.UniqueConstraint('user_id', 'conversation_with_id', name='unique_pinned_conversation'),
    )