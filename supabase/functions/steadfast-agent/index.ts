import "jsr:@supabase/functions-js/edge-runtime.d.ts";
const cors = {"Access-Control-Allow-Origin":"*","Access-Control-Allow-Headers":"authorization, apikey, content-type","Access-Control-Allow-Methods":"POST, OPTIONS"};
const reply=(data:unknown,status=200)=>new Response(JSON.stringify(data),{status,headers:{...cors,"Content-Type":"application/json"}});
Deno.serve(async(req:Request)=>{
 if(req.method==="OPTIONS")return new Response("ok",{headers:cors});
 if(req.method!=="POST")return reply({error:"POST required"},405);
 const base=Deno.env.get("SUPABASE_URL"),key=Deno.env.get("SUPABASE_ANON_KEY")??Deno.env.get("SUPABASE_PUBLISHABLE_KEY");
 const llmUrl=Deno.env.get("STEADFAST_LLM_URL")??"https://api.openai.com/v1/chat/completions",llmKey=Deno.env.get("STEADFAST_LLM_API_KEY"),model=Deno.env.get("STEADFAST_MODEL")??"gpt-4.1-mini",auth=req.headers.get("Authorization")??"";
 if(!base||!key)return reply({error:"Supabase function environment is incomplete."},500);
 if(!auth.startsWith("Bearer "))return reply({error:"Sign-in required."},401);
 try{
  const ur=await fetch(base+"/auth/v1/user",{headers:{apikey:key,Authorization:auth}});
  if(!ur.ok)return reply({error:"Invalid or expired session."},401);
  const user=await ur.json(),input=await req.json(),taskId=String(input.task_id??"");
  if(!/^[0-9a-f-]{36}$/i.test(taskId))return reply({error:"Valid task_id required."},400);
  const h={apikey:key,Authorization:auth,"Content-Type":"application/json"};
  const tr=await fetch(base+"/rest/v1/steadfast_tasks?id=eq."+taskId+"&select=id,goal,workspace_id,status",{headers:h});
  if(!tr.ok)return reply({error:"Could not read task."},403);
  const task=(await tr.json())[0];
  if(!task||task.status==="cancelled")return reply({error:"Task not found or cancelled."},404);
  if(!llmKey)return reply({error:"Add STEADFAST_LLM_API_KEY in Supabase Edge Function Secrets to enable AI execution.",setup_required:true},503);
  const patch=async(data:unknown)=>fetch(base+"/rest/v1/steadfast_tasks?id=eq."+taskId,{method:"PATCH",headers:{...h,Prefer:"return=minimal"},body:JSON.stringify(data)});
  const event=async(type:string,payload:unknown)=>fetch(base+"/rest/v1/steadfast_task_events",{method:"POST",headers:{...h,Prefer:"return=minimal"},body:JSON.stringify({task_id:taskId,actor_id:user.id,event_type:type,payload})});
  await patch({status:"running",updated_at:new Date().toISOString()});await event("agent.started",{model});
  let response:Response;
  try{response=await fetch(llmUrl,{method:"POST",headers:{Authorization:"Bearer "+llmKey,"Content-Type":"application/json"},body:JSON.stringify({model,messages:[{role:"system",content:"You are Steadfast, a careful goal-execution agent. Produce a concrete plan and useful reasoning. Never claim to have accessed external systems, changed files, run commands, or verified anything unless evidence/tools are supplied. Return JSON with summary (string), plan (string array), completed (string array), blockers (string array), next_actions (string array), knowledge_to_remember (array of {label,content,relation_hint}). Be honest about actions needing external tools or approval."},{role:"user",content:task.goal}],response_format:{type:"json_object"},temperature:0.2})})}catch{return reply({error:"Could not reach configured model endpoint."},502)}
  if(!response.ok){await patch({status:"failed",error:"Model endpoint returned HTTP "+response.status,updated_at:new Date().toISOString()});return reply({error:"Model endpoint returned HTTP "+response.status},502)}
  let provider:any;try{provider=JSON.parse(await response.text())}catch{return reply({error:"Model endpoint returned invalid JSON."},502)}
  const content=provider.choices?.[0]?.message?.content??provider.output_text??"";let result:any;
  try{result=typeof content==="string"?JSON.parse(content):content}catch{result={summary:String(content),plan:[],completed:[],blockers:["Model output was not valid JSON."],next_actions:[],knowledge_to_remember:[]}}
  const status=(result.blockers?.length&&!result.completed?.length)?"failed":"succeeded";
  await patch({status,result,plan:result.plan??[],error:status==="failed"?(result.blockers??[]).join("; "):null,updated_at:new Date().toISOString()});
  await event("agent.finished",{status,summary:result.summary??""});
  const memories=Array.isArray(result.knowledge_to_remember)?result.knowledge_to_remember.slice(0,10):[];
  for(const m of memories){if(typeof m.label!=="string"||typeof m.content!=="string"||!m.label.trim()||!m.content.trim())continue;await fetch(base+"/rest/v1/steadfast_knowledge_nodes",{method:"POST",headers:{...h,Prefer:"return=minimal"},body:JSON.stringify({workspace_id:task.workspace_id,created_by:user.id,node_type:"agent_insight",label:m.label.slice(0,500),content:m.content.slice(0,10000),source_task_id:taskId,confidence:0.65,metadata:{model,generated_by:"steadfast-agent"}})})}
  return reply({task_id:taskId,status,result,memories_saved:memories.length});
 }catch(e){return reply({error:e instanceof Error?e.message:"Unexpected agent error."},500)}
});