install https://cli.github.com/

git clone https://github.com/jctanner/odh-security-2.0
cd odh-security-2.0
virtualenv venv
source venv/bin/activate
pip install -r requirements.txt

./tool.py clone-forks
