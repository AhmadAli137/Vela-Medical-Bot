"""Extract local reference pages/keyframes for evidence inspection, not training."""
import json
from pathlib import Path
import subprocess
import pymupdf
from PIL import Image, ImageDraw

source = Path(r"C:\Users\Ahmad\Downloads")
out = Path("artifacts/references")
out.mkdir(parents=True,exist_ok=True)
pdf = pymupdf.open(source/"Bracket Bot Handout.pdf")
texts=[]
for i,page in enumerate(pdf):
    page.get_pixmap(matrix=pymupdf.Matrix(1.6,1.6)).save(str(out/f"handout-page-{i+1}.png"))
    texts.append(page.get_text())
(out/"handout.txt").write_text("\n\n".join(texts),encoding="utf-8")
metadata=[]
for prefix,name in (("camera","01 - Onboard Multi-Camera Views.mov"),("platform","02 - Bracket Bot Platform Demo.mov"),("teleop","03 - Meta Quest Teleoperation Demo.mp4")):
    path=source/name
    probe=json.loads(subprocess.check_output(["ffprobe","-v","error","-show_format","-show_streams","-of","json",str(path)]))
    duration=float(probe["format"]["duration"])
    frames=[]
    for i in range(9):
        seconds=duration*(i+.2)/9
        target=out/f"{prefix}-{i:02}.jpg"
        subprocess.run(["ffmpeg","-hide_banner","-loglevel","error","-ss",str(seconds),"-i",str(path),"-frames:v","1","-vf","scale=1280:-2","-y",str(target)],check=True)
        im=Image.open(target).convert("RGB")
        im.thumbnail((440,280))
        frame=Image.new("RGB",(460,310),"#111111")
        frame.paste(im,((460-im.width)//2,20))
        ImageDraw.Draw(frame).text((10,292),f"{prefix} {seconds:.1f}s",fill="white")
        frames.append(frame)
    sheet=Image.new("RGB",(1380,930),"black")
    for i,frame in enumerate(frames):
        sheet.paste(frame,((i%3)*460,(i//3)*310))
    sheet.save(out/f"{prefix}-contact-sheet.jpg",quality=94)
    metadata.append({"file":str(path),"duration_seconds":duration,"video_streams":[{k:s.get(k) for k in ('width','height','codec_name','r_frame_rate')} for s in probe['streams'] if s['codec_type']=='video']})
(out/"media.json").write_text(json.dumps(metadata,indent=2),encoding="utf-8")
print(json.dumps({"pages":len(pdf),"videos":metadata},indent=2))
