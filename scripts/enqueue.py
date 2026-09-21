"""Queue a fixed paid plan; read the operator token from a private file or env."""
import argparse,json,os,pathlib,ssl,sys,urllib.request
p=argparse.ArgumentParser();p.add_argument('kind',choices=['smoke','tournament']);p.add_argument('--url',default='https://jev-chess-bench.vercel.app');p.add_argument('--token-file');args=p.parse_args()
token=pathlib.Path(args.token_file).read_text().strip() if args.token_file else os.environ['ADMIN_TOKEN']
request=urllib.request.Request(args.url.rstrip('/')+'/api/runs',data=json.dumps({'kind':args.kind}).encode(),headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):return None
context=ssl.create_default_context()
if sys.platform=='darwin' and pathlib.Path('/etc/ssl/cert.pem').exists():context.load_verify_locations('/etc/ssl/cert.pem')
with urllib.request.build_opener(NoRedirect,urllib.request.HTTPSHandler(context=context)).open(request,timeout=30) as r:job=json.load(r)
print(json.dumps({'id':job['id'],'kind':job['kind'],'status':job['status'],'config':job['config']},indent=2))
