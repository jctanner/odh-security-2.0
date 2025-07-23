install https://cli.github.com/

git clone https://github.com/jctanner/odh-security-2.0
cd odh-security-2.0
virtualenv venv
source venv/bin/activate
pip install -r requirements.txt

# create all the clones
./tool.py clone-forks

# copy manifests into the operator repo
./tool.py workflow --name=manifests --exec

# do all the pre-deploy stuff
./tool.py workflow --name=pre-deploy --exec

# run the operator locally ...
cd src/opendatahub-operator
make run-nowebhook
