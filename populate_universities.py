import requests
import json
import sys
import time
from pathlib import Path
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

# Add the parent directory to Python path
sys.path.append(str(Path(__file__).parent))

from app import create_app, db
from app.models import University, Program

def fetch_universities_by_country(country):
    url = f"http://universities.hipolabs.com/search?country={country}"
    
    session = requests.Session()
    retries = Retry(
        total=5,
        backoff_factor=1,
        status_forcelist=[500, 502, 503, 504],
        allowed_methods=["GET"]
    )
    adapter = HTTPAdapter(max_retries=retries, pool_maxsize=10, pool_block=True)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json',
            'Accept-Encoding': 'gzip, deflate'
        }
        
        # Increase timeout and stream the response
        response = session.get(url, timeout=60, headers=headers, stream=True)
        response.raise_for_status()
        
        # Read the response in chunks
        content = ''
        for chunk in response.iter_content(chunk_size=8192, decode_unicode=True):
            if chunk:
                content += chunk
        
        return json.loads(content)
    except requests.exceptions.RequestException as e:
        print(f"Network error while fetching data for {country}: {str(e)}")
        return []
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON data for {country}: {str(e)}")
        return []
    except Exception as e:
        print(f"Unexpected error fetching data for {country}: {str(e)}")
        return []
    finally:
        session.close()

def populate_database():
    # Just focusing on US universities
    countries = ["United States"]
    
    common_programs = [
        "Computer Science",
        "Data Science",
        "Machine Learning",
        "Artificial Intelligence",
        "Software Engineering",
        "Information Technology",
        "Cybersecurity",
        "Web Development",
        "Cloud Computing",
        "Business Analytics"
    ]
    
    app = create_app()
    with app.app_context():
        total_universities = 0
        
        for country in countries:
            print(f"Fetching universities from {country}...")
            try:
                universities = fetch_universities_by_country(country)
                print(f"Found {len(universities)} universities in {country}")
                
                for uni_data in universities:
                    try:
                        # Clean up university name and check for valid data
                        uni_name = uni_data.get('name', '').strip()
                        if not uni_name:
                            continue
                            
                        # Check if university already exists
                        existing_uni = University.query.filter_by(name=uni_name).first()
                        if existing_uni:
                            print(f"Skipping existing university: {uni_name}")
                            continue
                        
                        # Create new university
                        university = University(
                            name=uni_name,
                            country=country,
                            domain=uni_data.get('domains', [None])[0]
                        )
                        db.session.add(university)
                        db.session.flush()
                        
                        # Add programs for this university
                        for program_name in common_programs:
                            program = Program(
                                name=program_name,
                                university_id=university.id
                            )
                            db.session.add(program)
                        
                        db.session.commit()
                        total_universities += 1
                        print(f"Added university: {university.name}")
                        
                    except Exception as e:
                        db.session.rollback()
                        print(f"Error adding university {uni_data.get('name', 'Unknown')}: {str(e)}")
                        continue
                
                print(f"\nSuccessfully added {total_universities} universities from {country}")
                
            except Exception as e:
                print(f"Error processing country {country}: {str(e)}")
                continue
        
        print(f"\nFinished! Added {total_universities} universities.")

if __name__ == "__main__":
    populate_database() 