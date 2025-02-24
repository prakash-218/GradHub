from flask import Blueprint, jsonify, request
from app.models import University, Program, Poll, PollOption, Vote
from app import db
import requests
from flask_login import current_user
import json
import os
from datetime import datetime, timedelta

api = Blueprint('api', __name__)
data_loaded = False
university_data = []

# Load universities from local JSON file
def load_university_data():
    """Load university data from local JSON file"""
    global data_loaded, university_data
    
    if data_loaded:
        return

    try:
        json_path = os.path.join(os.path.dirname(__file__), 'data', 'universities.json')
        with open(json_path, 'r', encoding='utf-8') as f:
            university_data = json.load(f)
        data_loaded = True
        print(f"Loaded {len(university_data)} universities from local file")
    except Exception as e:
        print(f"Error loading university data: {str(e)}")
        university_data = []

@api.route('/universities', methods=['GET'])
def get_universities():
    universities = University.query.all()
    return jsonify([{
        'id': u.id,
        'name': u.name,
        'country': u.country
    } for u in universities])

@api.route('/universities/<int:university_id>/programs', methods=['GET'])
def get_university_programs(university_id):
    programs = Program.query.filter_by(university_id=university_id).all()
    return jsonify([{
        'id': p.id,
        'name': p.name
    } for p in programs])

@api.route('/polls', methods=['POST'])
def create_poll():
    try:
        data = request.get_json()
        
        if not data.get('title') or not data.get('poll_type'):
            return jsonify({'error': 'Title and poll type are required'}), 400

        # Handle end_date with defaults and limits
        now = datetime.utcnow()
        default_end = now + timedelta(days=3)  # Default 3 days
        max_end = now + timedelta(days=10)     # Maximum 10 days
        min_end = now + timedelta(minutes=5)   # Must be at least 5 minutes in the future
        
        end_date = default_end
        if data.get('end_date'):
            try:
                requested_end = datetime.fromisoformat(data['end_date'].replace('Z', '+00:00'))
                # Ensure end date is at least 5 minutes in the future
                if requested_end <= min_end:
                    return jsonify({
                        'error': 'End date must be at least 5 minutes in the future',
                        'min_end_date': min_end.isoformat()
                    }), 400
                # Ensure end date is not more than 10 days away
                if requested_end > max_end:
                    return jsonify({
                        'error': 'End date cannot be more than 10 days from now',
                        'max_end_date': max_end.isoformat()
                    }), 400
                end_date = requested_end
            except ValueError:
                return jsonify({
                    'error': 'Invalid end date format. Please use ISO format (YYYY-MM-DDTHH:MM:SSZ)'
                }), 400

        # Create the poll with validated end date
        poll = Poll(
            title=data['title'],
            description=data.get('description', ''),
            poll_type=data['poll_type'],
            user_id=current_user.id if current_user.is_authenticated else None,
            course=data.get('course') if data['poll_type'] == 'university' else None,
            end_date=end_date  # Always set an end date
        )
        db.session.add(poll)
        db.session.flush()

        # Handle options based on poll type
        options = data.get('options', [])
        if len(options) < 2:
            return jsonify({'error': 'At least two options are required'}), 400

        if data['poll_type'] == 'university':
            if not data.get('course'):
                return jsonify({'error': 'Course is required for university polls'}), 400
                
            for uni in options:
                if not uni.get('name'):
                    return jsonify({'error': 'University name is required'}), 400
                
                option = PollOption(
                    poll_id=poll.id,
                    text=uni['name']
                )
                db.session.add(option)
        else:
            # For general polls, options is a list of strings
            for option_text in options:
                option = PollOption(
                    poll_id=poll.id,
                    text=option_text
                )
                db.session.add(option)

        # Add default "Just viewing results" option
        view_option = PollOption(
            poll_id=poll.id,
            text=Poll.DEFAULT_OPTION
        )
        db.session.add(view_option)

        db.session.commit()
        
        # Return the poll details including all relevant dates
        return jsonify({
            'message': 'Poll created successfully',
            'id': poll.id,
            'end_date': end_date.isoformat(),
            'default_end_date': default_end.isoformat(),
            'max_end_date': max_end.isoformat(),
            'min_end_date': min_end.isoformat()
        }), 201
        
    except Exception as e:
        db.session.rollback()
        print(f"Error creating poll: {e}")
        return jsonify({'error': 'Failed to create poll'}), 500

@api.route('/polls/<int:poll_id>', methods=['GET'])
def get_poll(poll_id):
    poll = Poll.query.get_or_404(poll_id)
    
    response = {
        'id': poll.id,
        'title': poll.title,
        'description': poll.description,
        'poll_type': poll.poll_type,
        'created_at': poll.created_at.isoformat(),
        'options': []
    }
    
    for option in poll.options:
        option_data = {
            'id': option.id,
            'text': option.text,
            'votes': option.votes.count()
        }
        # Add university-specific data only for university polls
        if poll.poll_type == 'university':
            option_data['university_domain'] = option.university_domain
            # Fetch additional university details if needed
            try:
                uni_details = fetch_university_details(option.university_domain)
                if uni_details:
                    option_data['university_details'] = uni_details
            except Exception as e:
                print(f"Error fetching university details: {str(e)}")
        
        response['options'].append(option_data)
    
    # Add total votes
    response['total_votes'] = sum(opt['votes'] for opt in response['options'])
    
    return jsonify(response)

@api.route('/polls/<int:poll_id>/vote', methods=['POST'])
def vote_poll(poll_id):
    data = request.get_json()
    option_id = data.get('option_id')
    
    if not option_id:
        return jsonify({'error': 'Option ID is required'}), 400
        
    try:
        poll_option = PollOption.query.get_or_404(option_id)
        
        # Verify option belongs to the correct poll
        if poll_option.poll_id != poll_id:
            return jsonify({'error': 'Invalid option for this poll'}), 400
        
        # Create new vote
        vote = Vote(option_id=option_id)
        db.session.add(vote)
        db.session.commit()
        
        # Return updated vote counts for all options in the poll
        options_data = [{
            'id': opt.id,
            'votes': opt.votes.count()
        } for opt in poll_option.poll.options]
        
        return jsonify({
            'message': 'Vote recorded successfully',
            'options': options_data,
            'total_votes': sum(opt['votes'] for opt in options_data)
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Error recording vote: {str(e)}")
        return jsonify({'error': 'Failed to record vote'}), 500

def fetch_university_details(domain):
    """Fetch specific university details using the domain"""
    url = "http://universities.hipolabs.com/search"
    params = {
        'domain': domain
    }
    
    try:
        response = requests.get(url, params=params, timeout=5)
        response.raise_for_status()
        universities = response.json()
        return universities[0] if universities else None
    except Exception as e:
        print(f"Error fetching university details: {str(e)}")
        return None

def fetch_universities(query):
    """Fetch universities based on search query"""
    url = "http://universities.hipolabs.com/search"
    params = {
        'country': 'United States',
        'name': query
    }
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json'
        }
        response = requests.get(url, params=params, headers=headers, timeout=5)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Error fetching universities: {str(e)}")
        return []

@api.route('/universities/search', methods=['GET'])
def search_universities():
    query = request.args.get('q', '').strip()
    print(f"Search query: '{query}'")  # Debug log
    
    if len(query) < 2:
        print("Query too short")  # Debug log
        return jsonify([])
    
    try:
        # Load data if not already loaded
        if not data_loaded:
            load_university_data()
        
        # Search for universities containing the query string
        query = query.lower()
        filtered = [
            {
                'name': uni['name'],
                'country': uni['country']
            }
            for uni in university_data
            if query in uni['name'].lower()
        ]
        
        filtered = filtered[:10]  # Limit to 10 results
        print(f"Found {len(filtered)} universities")  # Debug log
        for uni in filtered:
            print(f"- {uni['name']} ({uni['country']})")  # Debug log
            
        return jsonify(filtered)
        
    except Exception as e:
        print(f"Error in university search: {str(e)}")  # Debug error
        return jsonify({'error': str(e)}), 500

@api.route('/universities/<path:university_id>/programs/search', methods=['GET'])
def search_programs(university_id):
    query = request.args.get('q', '').strip().lower()
    if len(query) < 2:
        return jsonify([])
    
    # Get university details to customize program list
    university = fetch_university_details(university_id)
    
    # Base programs list - could be customized based on university type
    programs = {
        'Engineering & Technology': [
            "Computer Science",
            "Software Engineering",
            "Data Science",
            "Artificial Intelligence",
            "Machine Learning",
            "Computer Engineering",
            "Electrical Engineering",
            "Mechanical Engineering",
            "Civil Engineering",
            "Chemical Engineering",
            "Aerospace Engineering",
            "Robotics Engineering"
        ],
        'Business & Management': [
            "Business Administration",
            "Finance",
            "Marketing",
            "Accounting",
            "Economics",
            "International Business",
            "Business Analytics",
            "Management Information Systems",
            "Supply Chain Management",
            "Entrepreneurship"
        ],
        'Science & Mathematics': [
            "Physics",
            "Chemistry",
            "Biology",
            "Mathematics",
            "Statistics",
            "Environmental Science",
            "Neuroscience",
            "Biotechnology",
            "Applied Mathematics",
            "Quantum Computing"
        ],
        'Arts & Humanities': [
            "English Literature",
            "History",
            "Philosophy",
            "Psychology",
            "Sociology",
            "Communications",
            "Fine Arts",
            "Music",
            "Digital Media",
            "Graphic Design"
        ],
        'Health Sciences': [
            "Medicine",
            "Nursing",
            "Public Health",
            "Pharmacy",
            "Biomedical Engineering",
            "Health Informatics",
            "Physical Therapy",
            "Nutrition",
            "Dentistry",
            "Veterinary Medicine"
        ]
    }
    
    # Flatten the programs list
    all_programs = [prog for category in programs.values() for prog in category]
    
    # Filter programs based on search query
    filtered_programs = [
        prog for prog in all_programs
        if query in prog.lower()
    ]
    
    # Format the response
    formatted_programs = [{
        'id': str(idx),
        'name': prog_name,
        'university_id': university_id
    } for idx, prog_name in enumerate(sorted(filtered_programs))]
    
    return jsonify(formatted_programs[:15]) 