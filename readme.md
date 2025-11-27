Project for Hackathon Kita AI assistant for track "AI-Code Review Assistant".

## Installation guide

1. Clone this repository
2. Install dependencies:
```bash
pip install -r requirements.txt
```
3. Set up environment variables:
```bash
cp .env.example .env
```

## Pipeline

You will need to first connect the bot to GitLab repository, also make sure to specify the environment variables inside .env file.

1. Run webhook server for new MR `python real_world_case/1_webhook_for_new_mr.py`
2. Run webhook server for new commits `python real_world_case/2_webhook_for_new_commits.py`
3. Test by making a new MR using `python real_world_case/1_1_generation_of_new_MR.py`
4. Test by making a new commit using `python real_world_case/commit_simulator_from_junior.py`

After that you will be able to see the changes in the MR and commits in the GitLab repository with label by the Kita bot `reade-for-merge`.


![alt text](image.png)