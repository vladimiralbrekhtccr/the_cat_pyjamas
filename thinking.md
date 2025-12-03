So we fine-tuned the model because it was not following instructions well, and that allowes us to improve the performance of the model by 'n%'. We quantized model to fp-8 such that you as a user can use it on the 4090 GPU without any issues.


## If you use API 

## Typical problems of AI MR assistans.

1. They are not following instructions well.
2. They are slow
3. They are external

## So advantage of our solution if you use local LLM:
1. You don't pay for the API (Money Saving)
2. All the data is local and not send to any external services. (Security)
3. If you will have a new project, you can tune your model for this specific project, such that it will understand properly how to work with this project. (Tunable)




While out short-term memory was filled with the problem we want to receive some feedback such that we will understand here is might be a problem I should double check and our Assistand help with that, by providig immidiate feedback.




### TODOs:

1. Connect Nartay's evaluation pipeline vs Vladimir's open-source model calls.
* Basically make it easy to expriment with where we can change:
    * Model/Provider
    * MR difficulty
    * Amount of time spend on MR (can be controlled if we will create a local 'council of agents')
2. To improve the model understanding of the source code; Provide to the model not only diff but additional info for example code 50 lines above and below diff start and end. 
3. Nartay's pipeline 2.0 with <Thinking model>.
4. Experiment with Qwen3_30B_A3-fp-8 model because that will fit into 4090 GPU what might be huge advantage.
5. Prepare the speech and presentation.
6. Fine-tune Lora/model on small dataset with our instruction following format, such that we will show we can adapt the model for your specific case and on table show before fine-tuning and after how model started to produce more consistent scripts and following insturciton better. 



# The structure of the project



## Core
We have a BOT that monitors foe new MRs.

input from gitlab -->Agent A --> Agent B --> Output on gitlab

Agent A (lead)
Input:
1. MR diff / short_description / title
2. Possible to add the 
Output:
1. Review.


Agent B (coder)
Input:
1. MR diff / short_description / title
2. Review from the Agent A
Output:
1. Code suggestions

#TODOs:
1. Self-reflection after Agent B finishes.
2. 





## Eval

We have a seperate evaluation pipeline that uses this bot logic to evaluate different providers/models.
Input for this evaluation pipeline should be API from the bot right?

1. Generate repo
2. Generate MR
3. Generate tests?
4. ???





### What we want to improve:

1. Make webhooks using github repository internal webhooks.
2. 