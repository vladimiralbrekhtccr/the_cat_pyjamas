
### Env
```bash
uv venv --python 3.12 .venv
uva
uv pip install -r requirements.txt
```

Inside folder scripts you can run of of those:

Make sure to run it from main git folder.

```bash
bash scripts/run_evaluation.sh
bash scripts/run_webhook.sh
```

to test the model, you can use local of gemini provider.


<!-- 
# remove unnecessary commits
```bash
git checkout feature/full-mr-replay
git reset --hard 4efe69fe8b19ec300d297febd5c1b9a48d90a3c3
git push -f origin feature/full-mr-replay
``` -->