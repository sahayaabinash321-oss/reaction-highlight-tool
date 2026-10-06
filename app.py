from flask import Flask, render_template, request, jsonify, send_file
import os, subprocess, uuid, json, re

app = Flask(__name__)
BASE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(BASE, 'work')
os.makedirs(WORK, exist_ok=True)

def run(cmd):
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if p.returncode != 0:
        raise RuntimeError(p.stderr[-2500:])
    return p.stdout

def duration(path):
    out = run(['ffprobe','-v','error','-show_entries','format=duration','-of','default=noprint_wrappers=1:nokey=1',path])
    return float(out.strip())

def detect_scenes(path):
    # Scene changes are used as natural clip boundaries.
    p = subprocess.run(['ffmpeg','-i',path,'-filter:v',"select='gt(scene,0.32)',showinfo",'-f','null','-'],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    times=[]
    for line in p.stderr.splitlines():
        m=re.search(r'pts_time:([0-9.]+)', line)
        if m: times.append(float(m.group(1)))
    return times

def choose_highlights(total, scenes, target_min=60, target_max=180):
    # Generic automatic selector: sample energetic-looking scene-dense windows across the video.
    # Keeps complete windows and avoids hard 1-minute truncation.
    if total <= target_max:
        return [(0,total)]
    bounds=[0.0]+[x for x in scenes if 1 < x < total-1]+[total]
    # Build candidate 12-35 sec windows ending on scene boundaries.
    candidates=[]
    for i,s in enumerate(bounds[:-1]):
        for j in range(i+1, min(i+8,len(bounds))):
            e=bounds[j]
            d=e-s
            if 10 <= d <= 35:
                density=(j-i)/max(d,1)
                position_bonus=0.02 if s > total*0.15 else 0
                candidates.append((density+position_bonus,s,e))
    candidates.sort(reverse=True)
    picked=[]; used=0
    for _,s,e in candidates:
        if any(not (e <= a or s >= b) for a,b in picked):
            continue
        picked.append((s,e)); used += e-s
        if used >= min(target_max, max(target_min, total*0.08)):
            break
    if not picked:
        # fallback: three complete broad moments
        centers=[total*.25,total*.5,total*.75]
        picked=[(max(0,c-15),min(total,c+15)) for c in centers]
    picked=sorted(picked)
    # Never force a mid-content cut just to hit 180 exactly; allow modest overrun.
    return picked

@app.route('/')
def index(): return render_template('index.html')

@app.route('/process', methods=['POST'])
def process():
    url=(request.json or {}).get('url','').strip()
    if not url: return jsonify(error='YouTube link required'),400
    job=str(uuid.uuid4())[:8]; d=os.path.join(WORK,job); os.makedirs(d)
    src=os.path.join(d,'source.mp4')
    try:
        # Requires yt-dlp installed on the server.
        run(['yt-dlp','--no-playlist','-f','bv*[height<=720]+ba/b[height<=720]','--merge-output-format','mp4','-o',src,url])
        total=duration(src)
        scenes=detect_scenes(src)
        clips=choose_highlights(total,scenes)
        parts=[]
        for n,(s,e) in enumerate(clips):
            out=os.path.join(d,f'part{n}.mp4'); parts.append(out)
            run(['ffmpeg','-y','-ss',str(s),'-to',str(e),'-i',src,'-c:v','libx264','-preset','veryfast','-c:a','aac','-movflags','+faststart',out])
        listfile=os.path.join(d,'list.txt')
        with open(listfile,'w') as f:
            for x in parts: f.write("file '%s'\n" % x.replace("'","'\\''"))
        final=os.path.join(d,'highlight.mp4')
        run(['ffmpeg','-y','-f','concat','-safe','0','-i',listfile,'-c','copy',final])
        return jsonify(job=job, clips=[{'start':round(s,1),'end':round(e,1)} for s,e in clips],
                       duration=round(duration(final),1), video=f'/video/{job}')
    except Exception as e:
        return jsonify(error=str(e)),500

@app.route('/video/<job>')
def video(job):
    path=os.path.join(WORK,job,'highlight.mp4')
    if not os.path.exists(path): return 'Not found',404
    return send_file(path, mimetype='video/mp4', as_attachment=False, download_name='reaction-highlights.mp4')

if __name__ == '__main__':
    app.run(host='0.0.0.0',port=5000,debug=True)
