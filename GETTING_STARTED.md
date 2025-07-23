install https://cli.github.com/

```
git clone https://github.com/jctanner/odh-security-2.0
cd odh-security-2.0
virtualenv venv
source venv/bin/activate
pip install -r requirements.txt
```

### add your github token to a secrets file
```
echo $TOKEN > .github_token
```

### create all the clones
```
./tool.py clone-forks
```

### copy manifests into the operator repo
```
./tool.py workflow --name=manifests --exec
```

### do all the pre-deploy stuff
```
./tool.py workflow --name=pre-deploy --exec
```

### run the operator locally
```
cd src/opendatahub-operator
make run-nowebhook
```

### create the dsci
```
oc apply -f test.configs/dsci.yaml
```

Wait for status to be "ready" ...

```
watch oc get dsci
```

### create the dsc
```
oc apply -f test.configs/dsc.yaml
```

Wait for the status to be "ready" ...

```
watch oc get dsc
```

### setup the route + oauth-proxy in another terminal
```
./create_oauth_setup.sh
```
