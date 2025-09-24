Install https://cli.github.com/ as the code will use that for github + git operations.

```
git clone https://github.com/jctanner/odh-security-2.0
cd odh-security-2.0
virtualenv venv
source venv/bin/activate
pip install -r requirements.txt
```

### add your github API token to a secrets file
```
echo $TOKEN > .github_token
```

### create all the clones

This will clone every repo necessary to make a complete dev stack for ODH. If the repo doesn't exist in the org specified by config.yaml, it will be forked from the repo as defined in get_all_manifests.sh

```
./tool.py clone-forks
```

### copy manifests into the operator repo

This is an important step to follow if you want to use the manifests from your adjacent component checkouts. If you skip this, you'll end up with the default manifests as defined by the get_manifests.sh script.

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
