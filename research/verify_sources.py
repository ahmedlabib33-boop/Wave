"""Read-only checks; persist exact status, date, errors and bounded public metadata."""
import concurrent.futures, json, pathlib, datetime, httpx
ROOT=pathlib.Path(__file__).resolve().parent
checks={
 'adsb_docs':('https://api.adsb.lol/docs',{}),
 'adsb_openapi':('https://api.adsb.lol/openapi.json',{}),
 'adsb_cairo':('https://api.adsb.lol/v2/point/30.0878597/31.3413867/3',{}),
 'asf_docs':('https://docs.asf.alaska.edu/api/keywords/',{}),
 'asf_cairo':('https://api.daac.asf.alaska.edu/services/search/param',{'platform':'SENTINEL-1','intersectsWith':'POINT(31.3413867 30.0878597)','output':'geojson','maxResults':6,'processingLevel':'GRD_HD','end':'2026-11-05T23:59:59Z'}),
 'asf_reference':('https://api.daac.asf.alaska.edu/services/search/param',{'platform':'SENTINEL-1','intersectsWith':'POINT(31.3413867 30.0878597)','output':'geojson','maxResults':20,'start':'2026-10-31T00:00:00Z','end':'2026-11-01T00:00:00Z'}),
 'copernicus_docs':('https://documentation.dataspace.copernicus.eu/APIs/OData.html',{}),
 'copernicus_cairo':('https://catalogue.dataspace.copernicus.eu/odata/v1/Products',{'$filter':"Collection/Name eq 'SENTINEL-1' and OData.CSC.Intersects(area=geography'SRID=4326;POINT(31.3413867 30.0878597)')",'$top':3,'$orderby':'ContentDate/Start desc'}),
 'tomtom_docs':('https://developer.tomtom.com/traffic-api/documentation/traffic-flow/flow-segment-data',{}),
 'aisstream_docs':('https://aisstream.io/documentation',{}),
 'umbra_catalog':('https://umbra-open-data-catalog.s3.amazonaws.com/catalog.json',{}),
 'umbra_docs':('https://raw.githubusercontent.com/umbra-space/open-data/main/README.md',{}),
 'overpass_cairo':('https://overpass-api.de/api/interpreter',{'data':'[out:json][timeout:15];node(around:5000,30.0878597,31.3413867)["man_made"="surveillance"];out tags center 20;'}),
 'openaq_docs':('https://docs.openaq.org/',{}),
 'openaq_cairo':('https://api.openaq.org/v3/locations',{'coordinates':'30.0878597,31.3413867','radius':5000,'limit':10}),
 'rainviewer':('https://api.rainviewer.com/public/weather-maps.json',{}),
 'frigate_docs':('https://docs.frigate.video/configuration/object_filters/',{}),
 'onvif':('https://www.onvif.org/profiles/profile-s/',{}),
 'arkit':('https://developer.apple.com/documentation/arkit/ardepthdata',{}),
 'nearbyinteraction':('https://developer.apple.com/documentation/nearbyinteraction',{}),
 'radar_ti':('https://dev.ti.com/tirex/explore/node?node=A__AEHUBQX3C5Y9cQZSTeBLYw__radar_toolbox__1AslXXD__LATEST',{}),
 'fusion_filterpy':('https://filterpy.readthedocs.io/en/latest/',{}),
}
def run(item):
 key,(url,params)=item
 at=datetime.datetime.now(datetime.timezone.utc).isoformat()
 try:
  r=httpx.get(url,params=params,timeout=25,follow_redirects=True,headers={'User-Agent':'NileObserver/0.1 research (read-only)'})
  result={'id':key,'verified_at':at,'url':str(r.url),'status_code':r.status_code,'content_type':r.headers.get('content-type'),'bytes':len(r.content),'elapsed_ms':round(r.elapsed.total_seconds()*1000)}
  if r.status_code!=200: result['error']=r.text[:700]
  if 'json' in r.headers.get('content-type','') or key.endswith('catalog'):
   try:
    data=r.json(); (ROOT/(key+'.json')).write_text(json.dumps(data,ensure_ascii=False,indent=2))
    if isinstance(data,dict):result['keys']=list(data)[:25]
    if isinstance(data,dict) and 'features' in data:
     result['count']=len(data['features']); result['sample']=[x.get('properties') for x in data['features'][:2]]
    if key=='copernicus_cairo':result['sample']=data.get('value',[])[:1]
    if key=='adsb_cairo':result['sample']=data
   except ValueError:pass
  else: (ROOT/(key+'.html')).write_text(r.text)
  return result
 except Exception as e:return {'id':key,'verified_at':at,'url':url,'error':str(e),'status_code':None}
with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex: results=list(ex.map(run,checks.items()))
(ROOT/'verification.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
for x in results: print(x['id'],x.get('status_code'),x.get('count',''),str(x.get('error',''))[:160])
