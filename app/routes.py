from flask import Blueprint, render_template, flash, redirect, url_for, request, abort, jsonify, g
from flask_login import login_user, logout_user, login_required, current_user
from flask_wtf import FlaskForm
from app import db
from app.models import User, Poll, PollOption, Vote, Comment, AdmissionResult, Profile, Application, Follow, PollVote, Community, CommunityMembers, CommunityMessage, DirectMessage
from app.forms import LoginForm, RegistrationForm, PollForm, CommentForm, AdmissionResultForm, ProfileForm, ApplicationForm, CommunityForm
from datetime import datetime, timedelta
from urllib.parse import urlparse
from app.decorators import admin_required
from flask_wtf.csrf import generate_csrf

auth = Blueprint('auth', __name__)
main = Blueprint('main', __name__)

@auth.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user is None or not user.check_password(form.password.data):
            flash('Invalid email or password', 'danger')
            return redirect(url_for('auth.login'))
            
        login_user(user, remember=form.remember_me.data)
        print(f"User {user.username} logged in")
        flash('Welcome back, {}!'.format(user.username), 'success')
        
        # Get the next page from the request args
        next_page = request.args.get('next')
        if not next_page or urlparse(next_page).netloc != '':
            next_page = url_for('main.index')
            
        return redirect(next_page)

    print(f"Current user: {current_user}")
        
    return render_template('auth/login.html', form=form)

@auth.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(username=form.username.data, email=form.email.data)
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        flash('Congratulations, you are now registered!', 'success')
        return redirect(url_for('auth.login'))
    return render_template('auth/register.html', form=form)

@auth.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('main.index'))

@auth.route('/profile/<username>')
@login_required
def profile(username):
    user = User.query.filter_by(username=username).first_or_404()
    if user is None:
        abort(404)
    stats = {
        'total_polls': user.polls.count(),
        'total_votes': user.votes.count(),
        'total_comments': user.comments.count()
    }
    return render_template('auth/profile.html', user=user, stats=stats)

@main.route('/')
def index():
    page = request.args.get('page', 1, type=int)
    sort = request.args.get('sort', 'new')
    now = datetime.utcnow()
    
    # Base query for active polls (not ended)
    base_query = Poll.query.filter(
        db.or_(
            Poll.end_date.is_(None),  # No end date set
            Poll.end_date > now       # End date is in the future
        )
    )
    
    if sort == 'top':
        polls = base_query.join(PollVote).group_by(Poll.id)\
            .order_by(db.func.count(PollVote.id).desc())
    elif sort == 'trending':
        week_ago = now - timedelta(days=7)
        polls = base_query.join(PollVote)\
            .filter(PollVote.created_at > week_ago)\
            .group_by(Poll.id)\
            .order_by(db.func.count(PollVote.id).desc())
    else:  # 'new'
        polls = base_query.order_by(Poll.created_at.desc())
    
    polls = polls.paginate(page=page, per_page=10, error_out=False)

    if current_user.is_authenticated:
        pinned_conversations = current_user.pinned_conversations.all()
    else:
        pinned_conversations = []

    return render_template('index.html',
                         polls=polls,
                         sort=sort,
                         pinned_conversations=pinned_conversations)

@main.route('/create_poll', methods=['GET', 'POST'])
@login_required
def create_poll():
    form = PollForm()
    if form.validate_on_submit():
        poll = Poll(
            title=form.title.data,
            description=form.description.data,
            poll_type=form.poll_type.data,
            end_date=form.end_date.data,
            user_id=current_user.id
        )
        db.session.add(poll)
        db.session.commit()
        flash('Your poll has been created!', 'success')
        return redirect(url_for('main.view_poll', poll_id=poll.id))
    return render_template('create_poll.html', title='Create Poll', form=form)

@main.route('/poll/<int:poll_id>', methods=['GET'])
@login_required
def view_poll(poll_id):
    try:
        print(f"Attempting to view poll {poll_id}")
        poll = Poll.query.get_or_404(poll_id)
        print(f"Found poll: {poll.title}")
        
        # Get all root comments (no parent) for this poll, ordered by newest first
        root_comments = Comment.query.filter_by(
            poll_id=poll_id,
            parent_id=None
        ).order_by(Comment.created_at.desc()).all()
        
        print(f"Found {len(root_comments)} root comments")
        for comment in root_comments:
            print(f"Comment by {comment.author.username}: {comment.content[:50]}...")
        
        return render_template('view_poll.html', 
                             poll=poll,
                             root_comments=root_comments,
                             now=datetime.utcnow)
                             
    except Exception as e:
        print(f"Error in view_poll: {str(e)}")
        import traceback
        traceback.print_exc()
        flash('An error occurred while viewing the poll.', 'danger')
        return redirect(url_for('main.index'))

@main.route('/poll/<int:poll_id>/vote/<int:option_id>')
@login_required
def vote(poll_id, option_id):
    poll = Poll.query.get_or_404(poll_id)
    option = PollOption.query.get_or_404(option_id)
    
    if poll.end_date and poll.end_date < datetime.now():
        flash('This poll has ended', 'danger')
        return redirect(url_for('main.view_poll', poll_id=poll_id))
    
    # Check if user already voted
    existing_vote = Vote.query.filter_by(
        user_id=current_user.id,
        option_id=option_id
    ).first()
    
    if existing_vote:
        flash('You have already voted on this poll', 'warning')
    else:
        vote = Vote(user_id=current_user.id, option_id=option_id)
        db.session.add(vote)
        db.session.commit()
        flash('Your vote has been recorded!', 'success')
        
    return redirect(url_for('main.view_poll', poll_id=poll_id))

@main.route('/admissions')
def admissions():
    page = request.args.get('page', 1, type=int)
    results = AdmissionResult.query.order_by(
        AdmissionResult.created_at.desc()
    ).paginate(page=page, per_page=20)
    return render_template('admissions/index.html', results=results)

@main.route('/admissions/new', methods=['GET', 'POST'])
@login_required
def new_admission_result():
    form = AdmissionResultForm()
    if form.validate_on_submit():
        result = AdmissionResult(
            university=form.university.data,
            program=form.program.data,
            decision=form.decision.data,
            degree_type=form.degree_type.data,
            term=form.term.data,
            notification_date=form.notification_date.data,
            gpa=form.gpa.data,
            gre_verbal=form.gre_verbal.data,
            gre_quant=form.gre_quant.data,
            gre_awa=form.gre_awa.data,
            comments=form.comments.data,
            user_id=current_user.id
        )
        db.session.add(result)
        db.session.commit()
        flash('Your admission result has been posted!', 'success')
        return redirect(url_for('main.admissions'))
    return render_template('admissions/new.html', form=form)

@main.route('/search')
def search():
    query = request.args.get('q', '')
    polls = Poll.query.filter(
        (Poll.title.ilike(f'%{query}%') | 
         Poll.description.ilike(f'%{query}%')) &
        ((Poll.visibility == Poll.PUBLIC) | 
         (Poll.user_id == current_user.id))
    ).order_by(Poll.created_at.desc())
    return render_template('search.html', polls=polls, query=query)

@main.route('/poll/<int:poll_id>/share')
def share_poll(poll_id):
    poll = Poll.query.get_or_404(poll_id)
    share_url = url_for('main.view_poll', poll_id=poll_id, _external=True)
    return render_template('share_poll.html', poll=poll, share_url=share_url)

@main.route('/admin')
@login_required
@admin_required
def admin_dashboard():
    stats = {
        'total_users': User.query.count(),
        'total_polls': Poll.query.count(),
        'total_votes': Vote.query.count(),
        'active_polls': Poll.query.filter(
            (Poll.end_date > datetime.utcnow()) | 
            (Poll.end_date == None)
        ).count()
    }
    return render_template('admin/dashboard.html', stats=stats)

@main.route('/admin/users')
@login_required
@admin_required
def admin_users():
    users = User.query.all()
    return render_template('admin/users.html', users=users)

@main.route('/admin/make_admin/<int:user_id>')
@login_required
@admin_required
def make_admin(user_id):
    user = User.query.get_or_404(user_id)
    user.is_admin = True
    db.session.commit()
    flash(f'Made {user.username} an admin.', 'success')
    return redirect(url_for('main.admin_users'))

@main.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    # Create profile if it doesn't exist
    if not hasattr(current_user, 'profile') or current_user.profile is None:
        profile = Profile(user_id=current_user.id)
        db.session.add(profile)
        db.session.commit()
        db.session.refresh(current_user)
    
    form = ProfileForm(obj=current_user.profile)
    
    if request.method == 'GET':
        return render_template('users/profile.html', 
                             user=current_user, 
                             profile=current_user.profile,
                             is_following=False)
    
    if form.validate_on_submit():
        try:
            # Verify and update each field individually
            if form.university.data:
                current_user.profile.university = form.university.data
            if form.major.data:
                current_user.profile.major = form.major.data
            if form.gpa.data is not None:
                current_user.profile.gpa = form.gpa.data
            if form.gpa_scale.data is not None:
                current_user.profile.gpa_scale = form.gpa_scale.data
            
            # Test Scores - only update if provided
            if form.toefl_score.data is not None:
                current_user.profile.toefl_score = form.toefl_score.data
            if form.ielts_score.data is not None:
                current_user.profile.ielts_score = form.ielts_score.data
            if form.gre_verbal.data is not None:
                current_user.profile.gre_verbal = form.gre_verbal.data
            if form.gre_quant.data is not None:
                current_user.profile.gre_quant = form.gre_quant.data
            if form.gre_awa.data is not None:
                current_user.profile.gre_awa = form.gre_awa.data
            
            # Work Experience
            if form.work_experience_years.data is not None:
                current_user.profile.work_experience_years = form.work_experience_years.data
            if form.current_job.data:
                current_user.profile.current_job = form.current_job.data
            if form.company.data:
                current_user.profile.company = form.company.data
            
            # Research Experience
            if form.research_experience.data:
                current_user.profile.research_experience = form.research_experience.data
            if form.publications.data:
                current_user.profile.publications = form.publications.data
            
            # Additional Information
            if form.target_term.data:
                current_user.profile.target_term = form.target_term.data
            if form.target_degree.data:
                current_user.profile.target_degree = form.target_degree.data
            if form.target_major.data:
                current_user.profile.target_major = form.target_major.data
            
            # Bio
            if form.bio.data:
                current_user.profile.bio = form.bio.data
            
            db.session.commit()
            flash('Your profile has been updated!', 'success')
            return redirect(url_for('main.profile'))
            
        except Exception as e:
            db.session.rollback()
            flash('Error updating profile. Please try again.', 'danger')
            print(f"Error updating profile: {e}")
    
    return render_template('profile/edit.html', form=form)

@main.route('/profile/view')
@login_required
def view_profile():
    return render_template('profile/view.html')

@main.route('/profile/edit', methods=['GET', 'POST'])
@login_required
def edit_profile():
    # Create profile if it doesn't exist
    if not hasattr(current_user, 'profile') or current_user.profile is None:
        profile = Profile(user_id=current_user.id)
        db.session.add(profile)
        db.session.commit()
        db.session.refresh(current_user)
    
    form = ProfileForm(obj=current_user.profile)
    
    if form.validate_on_submit():
        try:
            # Verify and update each field individually
            if form.university.data:
                current_user.profile.university = form.university.data
            if form.major.data:
                current_user.profile.major = form.major.data
            if form.gpa.data is not None:
                current_user.profile.gpa = form.gpa.data
            if form.gpa_scale.data is not None:
                current_user.profile.gpa_scale = form.gpa_scale.data
            
            # Test Scores - only update if provided
            if form.toefl_score.data is not None:
                current_user.profile.toefl_score = form.toefl_score.data
            if form.ielts_score.data is not None:
                current_user.profile.ielts_score = form.ielts_score.data
            if form.gre_verbal.data is not None:
                current_user.profile.gre_verbal = form.gre_verbal.data
            if form.gre_quant.data is not None:
                current_user.profile.gre_quant = form.gre_quant.data
            if form.gre_awa.data is not None:
                current_user.profile.gre_awa = form.gre_awa.data
            
            # Work Experience
            if form.work_experience_years.data is not None:
                current_user.profile.work_experience_years = form.work_experience_years.data
            if form.current_job.data:
                current_user.profile.current_job = form.current_job.data
            if form.company.data:
                current_user.profile.company = form.company.data
            
            # Research Experience
            if form.research_experience.data:
                current_user.profile.research_experience = form.research_experience.data
            if form.publications.data:
                current_user.profile.publications = form.publications.data
            
            # Additional Information
            if form.target_term.data:
                current_user.profile.target_term = form.target_term.data
            if form.target_degree.data:
                current_user.profile.target_degree = form.target_degree.data
            if form.target_major.data:
                current_user.profile.target_major = form.target_major.data
            
            # Bio
            if form.bio.data:
                current_user.profile.bio = form.bio.data
            
            db.session.commit()
            flash('Your profile has been updated!', 'success')
            return redirect(url_for('main.profile'))
            
        except Exception as e:
            db.session.rollback()
            flash('Error updating profile. Please try again.', 'danger')
            print(f"Error updating profile: {e}")
    
    return render_template('profile/edit.html', form=form)

@main.route('/applications/new', methods=['GET', 'POST'])
@login_required
def new_application():
    form = ApplicationForm()
    if form.validate_on_submit():
        application = Application(
            user_id=current_user.id,
            university=form.university.data,
            program=form.program.data,
            term=form.term.data,
            degree_type=form.degree_type.data,
            status=form.status.data,
            applied_date=form.applied_date.data,
            deadline=form.deadline.data,
            decision_date=form.decision_date.data,
            application_fee=form.application_fee.data,
            fee_paid=form.fee_paid.data,
            transcripts_submitted=form.transcripts_submitted.data,
            lors_submitted=form.lors_submitted.data,
            sop_submitted=form.sop_submitted.data,
            resume_submitted=form.resume_submitted.data,
            notes=form.notes.data
        )
        db.session.add(application)
        db.session.commit()
        flash('Application added successfully!', 'success')
        return redirect(url_for('main.applications'))
    return render_template('applications/manage.html', form=form)

@main.route('/applications/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit_application(id):
    application = Application.query.get_or_404(id)
    if application.user_id != current_user.id:
        abort(403)
    
    form = ApplicationForm(obj=application)
    if form.validate_on_submit():
        form.populate_obj(application)
        db.session.commit()
        flash('Application updated successfully!', 'success')
        return redirect(url_for('main.applications'))
    return render_template('applications/manage.html', form=form, application=application)

@main.route('/applications')
@login_required
def applications():
    applications = Application.query.filter_by(user_id=current_user.id)\
        .order_by(Application.created_at.desc()).all()
    return render_template('applications/index.html', applications=applications)

@main.route('/applications/flow')
@login_required
def application_flow():
    applications = Application.query.filter_by(user_id=current_user.id).all()
    
    # Prepare data for Sankey diagram
    data = {
        'total': len(applications),
        'universities': {},
        'decisions': {
            'Applied': 0,
            'Interview': 0,
            'Accepted': 0,
            'Rejected': 0,
            'Waitlisted': 0,
            'Seat Locked': 0
        }
    }
    
    for app in applications:
        uni_program = f"{app.university} - {app.program}"
        if uni_program not in data['universities']:
            data['universities'][uni_program] = {
                'count': 1,
                'status': app.status
            }
        else:
            data['universities'][uni_program]['count'] += 1
        
        data['decisions'][app.status] = data['decisions'].get(app.status, 0) + 1
    
    return render_template('applications/flow.html', data=data)

@main.route('/toggle_privacy', methods=['POST'])
@login_required
def toggle_privacy():
    current_user.is_private = not current_user.is_private
    db.session.commit()
    return jsonify({'is_private': current_user.is_private})

@main.route('/follow/<int:user_id>', methods=['POST'])
@login_required
def follow(user_id):
    if not request.is_json:
        return jsonify({'error': 'Invalid request'}), 400
        
    user = User.query.get_or_404(user_id)
    if user == current_user:
        return jsonify({'error': 'Cannot follow yourself'}), 400
    
    if user.is_private:
        if not current_user.has_follow_request_pending(user):
            current_user.send_follow_request(user)
            db.session.commit()
            return jsonify({'message': 'Follow request sent'})
        return jsonify({'message': 'Follow request already sent'})
    else:
        if not current_user.is_following(user):
            current_user.follow(user)
            db.session.commit()
            return jsonify({'message': 'Following'})
        return jsonify({'message': 'Already following'})

@main.route('/unfollow/<int:user_id>', methods=['POST'])
@login_required
def unfollow(user_id):
    if not request.is_json:
        return jsonify({'error': 'Invalid request'}), 400
        
    user = User.query.get_or_404(user_id)
    if user == current_user:
        return jsonify({'error': 'Cannot unfollow yourself'}), 400
    
    current_user.unfollow(user)
    db.session.commit()
    return jsonify({'message': 'Unfollowed'})

@main.route('/accept_follow/<int:user_id>', methods=['POST'])
@login_required
def accept_follow(user_id):
    if not request.is_json:
        return jsonify({'error': 'Invalid request'}), 400
        
    user = User.query.get_or_404(user_id)
    request_exists = current_user.follow_requests_received.filter_by(requester_id=user_id).first()
    
    if not request_exists:
        return jsonify({'error': 'No follow request found'}), 404
    
    try:
        current_user.accept_follow_request(user)
        db.session.commit()
        return jsonify({'message': 'Follow request accepted'})
    except Exception as e:
        db.session.rollback()
        print(f"Error accepting follow request: {e}")
        return jsonify({'error': 'Failed to accept follow request'}), 500

@main.route('/reject_follow/<int:user_id>', methods=['POST'])
@login_required
def reject_follow(user_id):
    if not request.is_json:
        return jsonify({'error': 'Invalid request'}), 400
        
    user = User.query.get_or_404(user_id)
    request_exists = current_user.follow_requests_received.filter_by(requester_id=user_id).first()
    
    if not request_exists:
        return jsonify({'error': 'No follow request found'}), 404
    
    try:
        current_user.reject_follow_request(user)
        db.session.commit()
        return jsonify({'message': 'Follow request rejected'})
    except Exception as e:
        db.session.rollback()
        print(f"Error rejecting follow request: {e}")
        return jsonify({'error': 'Failed to reject follow request'}), 500

@main.route('/user/<username>')
@login_required
def view_user_profile(username):
    user = User.query.filter_by(username=username).first_or_404()
    
    # Check if profile is accessible
    can_view = (
        user == current_user or  # It's your own profile
        not user.is_private or   # Profile is public
        current_user.is_following(user)  # You're a follower
    )
    
    if not can_view:
        flash('This profile is private. Send a follow request to view.', 'warning')
        return redirect(url_for('main.search_users'))
    
    # Get user's data
    applications = user.applications if hasattr(user, 'applications') else []
    polls = user.polls.order_by(Poll.created_at.desc()).all() if hasattr(user, 'polls') else []
    profile = user.profile  # Get the profile information
    
    # Prepare Sankey data
    if applications:
        status_counts = {}
        universities = {}
        
        for app in applications:
            # Count applications by status
            status_counts[app.status] = status_counts.get(app.status, 0) + 1
            
            # Group universities by status
            if app.status not in universities:
                universities[app.status] = {}
            universities[app.status][app.university] = universities[app.status].get(app.university, 0) + 1
        
        sankey_data = {
            'statusCounts': status_counts,
            'universities': universities
        }
    else:
        sankey_data = None

    return render_template('users/profile.html', 
                         user=user,
                         profile=profile,
                         applications=applications,
                         polls=polls,
                         sankey_data=sankey_data,
                         is_following=current_user.is_following(user))

@main.route('/users/search')
@login_required
def search_users():
    query = request.args.get('q', '')
    if query:
        users = User.query.filter(User.username.ilike(f'%{query}%')).all()
    else:
        users = []
    return render_template('users/search.html', users=users, query=query)

@main.route('/follow-requests')
@login_required
def follow_requests():
    # Get both received and sent requests
    received_requests = current_user.follow_requests_received.all()
    sent_requests = current_user.follow_requests_sent.all()
    return render_template('users/follow_requests.html', 
                         received_requests=received_requests,
                         sent_requests=sent_requests)

@main.route('/user/<username>/followers')
@login_required
def user_followers(username):
    user = User.query.filter_by(username=username).first_or_404()
    
    # Check if profile is accessible
    can_view = (
        user == current_user or
        not user.is_private or
        current_user.is_following(user)
    )
    
    if not can_view:
        flash('This profile is private. Send a follow request to view.', 'warning')
        return redirect(url_for('main.search_users'))
    
    # Get followers from the Follow model
    followers = db.session.query(User).\
        join(Follow, Follow.follower_id == User.id).\
        filter(Follow.followed_id == user.id).\
        order_by(User.username).all()
    
    return render_template('users/followers.html', 
                         user=user,
                         followers=followers,
                         title="Followers")

@main.route('/user/<username>/following')
@login_required
def user_following(username):
    user = User.query.filter_by(username=username).first_or_404()
    
    # Check if profile is accessible
    can_view = (
        user == current_user or
        not user.is_private or
        current_user.is_following(user)
    )
    
    if not can_view:
        flash('This profile is private. Send a follow request to view.', 'warning')
        return redirect(url_for('main.search_users'))
    
    # Get following from the Follow model
    following = db.session.query(User).\
        join(Follow, Follow.followed_id == User.id).\
        filter(Follow.follower_id == user.id).\
        order_by(User.username).all()
    
    return render_template('users/followers.html', 
                         user=user,
                         followers=following,
                         title="Following")

@main.route('/poll/<int:poll_id>/comment', methods=['POST'])
@login_required
def add_comment(poll_id):
    try:
        print(f"Received comment request for poll {poll_id}")
        print(f"Request headers: {request.headers}")
        print(f"Request data: {request.get_data()}")
        data = request.get_json()
        print(f"Parsed JSON data: {data}")
        
        if not data or not data.get('content'):
            print("No content provided")
            return jsonify({'error': 'Comment content is required'}), 400
            
        poll = Poll.query.get_or_404(poll_id)
        print(f"Found poll: {poll.title}")
        
        # Create the comment
        comment = Comment(
            content=data['content'],
            poll_id=poll_id,
            author_id=current_user.id,
            created_at=datetime.utcnow()
        )
        
        print(f"Created comment object: {comment.content[:50]}...")
        db.session.add(comment)
        db.session.commit()
        print(f"Saved comment with ID: {comment.id}")
        
        # Render the comment HTML
        comment_html = render_template('poll/_comment.html', 
                                     comment=comment,
                                     current_user=current_user)
        print("Rendered comment HTML")
        
        return jsonify({
            'message': 'Comment added successfully',
            'html': comment_html,
            'comment_id': comment.id
        }), 201
        
    except Exception as e:
        db.session.rollback()
        print(f"Error adding comment: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Failed to add comment: {str(e)}'}), 500

@main.route('/poll/comment/<int:comment_id>/delete', methods=['POST'])
@login_required
def delete_comment(comment_id):
    try:
        comment = Comment.query.get_or_404(comment_id)
        
        if comment.author != current_user:
            return jsonify({'error': 'Unauthorized'}), 403
            
        db.session.delete(comment)
        db.session.commit()
        
        return jsonify({'message': 'Comment deleted successfully'}), 200
        
    except Exception as e:
        db.session.rollback()
        print(f"Error deleting comment: {e}")
        return jsonify({'error': 'Failed to delete comment'}), 500

@main.route('/poll/<int:poll_id>/reply', methods=['POST'])
@login_required
def add_reply(poll_id):
    try:
        data = request.get_json()
        
        if not data or not data.get('content') or not data.get('parent_id'):
            return jsonify({'error': 'Reply content and parent comment ID are required'}), 400
            
        parent_comment = Comment.query.get_or_404(data['parent_id'])
        
        if parent_comment.poll_id != poll_id:
            return jsonify({'error': 'Invalid parent comment'}), 400
            
        reply = Comment(
            content=data['content'],
            author=current_user,
            poll_id=poll_id,
            parent_id=parent_comment.id
        )
        
        db.session.add(reply)
        db.session.commit()
        
        # Render the new reply HTML
        reply_html = render_template('poll/_comment.html', comment=reply)
        
        return jsonify({
            'message': 'Reply added successfully',
            'html': reply_html,
            'comment_id': reply.id
        }), 201
        
    except Exception as e:
        db.session.rollback()
        print(f"Error adding reply: {e}")
        return jsonify({'error': 'Failed to add reply'}), 500

@main.route('/poll/<int:poll_id>/upvote', methods=['POST'])
@login_required
def upvote_poll(poll_id):
    poll = Poll.query.get_or_404(poll_id)
    
    try:
        # Check if vote already exists
        existing_vote = PollVote.query.filter_by(
            user_id=current_user.id,
            poll_id=poll.id
        ).first()
        
        if existing_vote:
            # Remove upvote
            db.session.delete(existing_vote)
            db.session.commit()
            return jsonify({'status': 'removed', 'count': poll.upvote_count})
        else:
            # Add upvote
            vote = PollVote(user_id=current_user.id, poll_id=poll.id)
            db.session.add(vote)
            db.session.commit()
            return jsonify({'status': 'added', 'count': poll.upvote_count})
            
    except Exception as e:
        db.session.rollback()
        print(f"Error handling upvote: {e}")
        return jsonify({'error': 'Failed to process upvote'}), 500

@main.route('/archived')
def archived_polls():
    page = request.args.get('page', 1, type=int)
    now = datetime.utcnow()
    
    # Get polls that have ended
    archived_polls = Poll.query.filter(
        Poll.end_date <= now  # End date has passed
    ).order_by(Poll.created_at.desc())
    
    polls = archived_polls.paginate(page=page, per_page=10, error_out=False)
    return render_template('archived_polls.html', polls=polls)

@main.route('/communities')
@login_required
def communities():
    # Get all communities or filter by search
    search = request.args.get('search', '')
    if search:
        communities = Community.query.filter(
            db.or_(
                Community.university.ilike(f'%{search}%'),
                Community.program.ilike(f'%{search}%')
            )
        ).order_by(Community.created_at.desc()).all()
    else:
        communities = Community.query.order_by(Community.created_at.desc()).all()
    
    return render_template('communities/index.html', communities=communities)

@main.route('/communities/create', methods=['GET', 'POST'])
@login_required
def create_community():
    form = CommunityForm()
    if form.validate_on_submit():
        try:
            # Check for existing community
            existing = Community.query.filter_by(
                university=form.university.data,
                program=form.program.data
            ).first()
            
            if existing:
                flash('A community for this university and program already exists!', 'warning')
                return redirect(url_for('main.view_community', id=existing.id))
            
            # Create new community
            community = Community(
                name=f"{form.university.data} - {form.program.data}",
                university=form.university.data,
                program=form.program.data,
                description=form.description.data,
                created_by_id=current_user.id
            )
            
            # Add creator as first member
            db.session.add(community)
            db.session.flush()  # Get community ID
            
            membership = CommunityMembers(
                user_id=current_user.id,
                community_id=community.id
            )
            
            db.session.add(membership)
            db.session.commit()
            
            flash('Community created successfully!', 'success')
            return redirect(url_for('main.view_community', id=community.id))
            
        except Exception as e:
            db.session.rollback()
            flash('Error creating community. Please try again.', 'danger')
            print(f"Error creating community: {e}")
    
    return render_template('communities/create.html', form=form)

@main.route('/communities/<int:id>')
@login_required
def view_community(id):
    community = Community.query.get_or_404(id)
    messages = community.messages.order_by(CommunityMessage.created_at.desc()).limit(100).all()
    is_member = current_user in community.members
    form = FlaskForm()  # Empty form for CSRF token
    
    return render_template('communities/view.html',
                         community=community,
                         messages=messages,
                         is_member=is_member,
                         form=form)

@main.route('/communities/<int:id>/join', methods=['POST'])
@login_required
def join_community(id):
    form = FlaskForm()  # Empty form for CSRF validation
    if form.validate_on_submit():
        community = Community.query.get_or_404(id)
        
        if current_user in community.members:
            flash('You are already a member of this community!', 'info')
            return redirect(url_for('main.view_community', id=id))
        
        membership = CommunityMembers(user_id=current_user.id, community_id=id)
        db.session.add(membership)
        db.session.commit()
        
        flash('You have joined the community!', 'success')
        return redirect(url_for('main.view_community', id=id))
    
    return redirect(url_for('main.view_community', id=id))

@main.route('/communities/<int:id>/message', methods=['POST'])
@login_required
def post_message(id):
    if not request.is_json:
        return jsonify({'error': 'Invalid request'}), 400
        
    community = Community.query.get_or_404(id)
    if current_user not in community.members:
        return jsonify({'error': 'You must be a member to post messages'}), 403
    
    data = request.get_json()
    if not data.get('content'):
        return jsonify({'error': 'Message content is required'}), 400
    
    try:
        message = CommunityMessage(
            content=data['content'],
            user_id=current_user.id,
            community_id=id
        )
        db.session.add(message)
        db.session.commit()
        
        # Return the new message HTML
        message_html = render_template('communities/_message.html', message=message)
        return jsonify({
            'message': 'Message posted successfully',
            'html': message_html
        }), 201
        
    except Exception as e:
        db.session.rollback()
        print(f"Error posting message: {e}")
        return jsonify({'error': 'Failed to post message'}), 500

@main.route('/communities/<int:id>/pin', methods=['POST'])
@login_required
def pin_community(id):
    community = Community.query.get_or_404(id)
    if community not in current_user.pinned_communities:
        current_user.pinned_communities.append(community)
        db.session.commit()
        return jsonify({'status': 'pinned'})
    return jsonify({'status': 'already_pinned'})

@main.route('/communities/<int:id>/unpin', methods=['POST'])
@login_required
def unpin_community(id):
    community = Community.query.get_or_404(id)
    if community in current_user.pinned_communities:
        current_user.pinned_communities.remove(community)
        db.session.commit()
        return jsonify({'status': 'unpinned'})
    return jsonify({'status': 'not_pinned'})

@main.route('/messages', defaults={'user_id': None})
@main.route('/messages/<int:user_id>', methods=['GET', 'POST'])
@login_required
def chat(user_id):
    if user_id is None:
        return render_template('messages/chat.html',
                             other_user=None,
                             following=current_user.following.all())
    
    other_user = User.query.get_or_404(user_id)
    
    # Check if current user is following the recipient
    if not current_user.is_following(other_user):
        flash('You can only message users you follow.', 'warning')
        return redirect(url_for('main.messages'))
    
    if request.method == 'POST':
        content = request.form.get('content')
        if content:
            message = DirectMessage(
                sender_id=current_user.id,
                recipient_id=user_id,
                content=content
            )
            db.session.add(message)
            db.session.commit()
            
            # Check if it's an AJAX request
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({
                    'status': 'success',
                    'html': render_template('messages/_message.html', message=message)
                })
            return redirect(url_for('main.chat', user_id=user_id))
    
    messages = DirectMessage.query.filter(
        ((DirectMessage.sender_id == current_user.id) & (DirectMessage.recipient_id == user_id)) |
        ((DirectMessage.sender_id == user_id) & (DirectMessage.recipient_id == current_user.id))
    ).order_by(DirectMessage.created_at.asc()).all()
    
    return render_template('messages/chat.html', 
                         other_user=other_user,
                         messages=messages,
                         following=current_user.following.all())

@main.route('/messages/<int:user_id>/load')
@login_required
def load_messages(user_id):
    other_user = User.query.get_or_404(user_id)
    messages = DirectMessage.query.filter(
        ((DirectMessage.sender_id == current_user.id) & (DirectMessage.recipient_id == user_id)) |
        ((DirectMessage.sender_id == user_id) & (DirectMessage.recipient_id == current_user.id))
    ).order_by(DirectMessage.created_at.asc()).all()
    
    return render_template('messages/_message_list.html', 
                         messages=messages,
                         other_user=other_user)

@main.route('/messages/<int:user_id>/pin', methods=['POST'])
@login_required
def pin_conversation(user_id):
    try:
        user = User.query.get_or_404(user_id)
        if user == current_user:
            return jsonify({'error': 'Cannot pin conversation with yourself'}), 400
        
        if user not in current_user.pinned_conversations:
            current_user.pinned_conversations.append(user)
            db.session.commit()
            return jsonify({'status': 'success'})
        return jsonify({'status': 'already_pinned'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@main.route('/messages/<int:user_id>/unpin', methods=['POST'])
@login_required
def unpin_conversation(user_id):
    try:
        user = User.query.get_or_404(user_id)
        if user in current_user.pinned_conversations:
            current_user.pinned_conversations.remove(user)
            db.session.commit()
            return jsonify({'status': 'success'})
        return jsonify({'status': 'not_pinned'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@main.after_request
def add_csrf_token(response):
    response.set_cookie('csrf_token', generate_csrf())
    return response 