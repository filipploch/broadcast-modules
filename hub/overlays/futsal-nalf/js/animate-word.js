function animateWord(
    elementId,
    word,
    duration,
    elementToHideId,
    class1,
    class2,
    teamName14,
    cellSize
){
const container = document.getElementById(elementId);
if(!container) return;

const elementToHide = elementToHideId ? document.getElementById(elementToHideId) : null;
if(elementToHide) elementToHide.style.visibility="hidden";

container.innerHTML="";

const fontSize = cellSize*0.6;
const teamFont = cellSize*0.55;

const wordContainer = document.createElement("div");
wordContainer.style.display="inline-flex";
wordContainer.style.position="relative";
wordContainer.style.opacity="0";
wordContainer.style.height=cellSize+"px";
wordContainer.style.width=0;
wordContainer.style.willChange="transform,opacity,background";
wordContainer.style.transform="translateZ(0)";
container.appendChild(wordContainer);

requestAnimationFrame(()=>wordContainer.style.opacity="1");

const charSpans=[];
let _wordContainerWidth = 0;
for(let char of word){
    const box=document.createElement("div");
    box.style.width=cellSize+"px";
    box.style.height=cellSize+"px";
    box.style.display="flex";
    box.style.alignItems="center";
    box.style.justifyContent="center";
    addClassName(box, 'charBox');

    _wordContainerWidth += cellSize;

    const span=document.createElement("span");
    span.textContent=char;
    span.style.fontSize=fontSize+"px";
    span.style.display="inline-block";
    span.style.transform="scale(1)";
    span.style.willChange="transform,color";

    box.appendChild(span);
    wordContainer.appendChild(box);
    charSpans.push(span);
}

wordContainer.style.width = _wordContainerWidth+"px";

// ---------- helpers ----------

const easeOutBack = t => 1 + (--t)*t*(2.7*t+1.7);

function hexToRgb(hex){
hex=hex.replace("#","");
return [
parseInt(hex.substring(0,2),16),
parseInt(hex.substring(2,4),16),
parseInt(hex.substring(4,6),16)
];
}

function rgbToHex(r,g,b){
return "#"+[r,g,b].map(v=>{
const h=v.toString(16);
return h.length==1?"0"+h:h;
}).join("");
}

function darken(rgb,percent){
return rgb.map(v=>Math.max(0,Math.floor(v*(1-percent))));
}

function gradientFrom(rgb){
const dark=darken(rgb,0.1);
return `linear-gradient(to bottom,
rgb(${rgb[0]},${rgb[1]},${rgb[2]}),
rgb(${dark[0]},${dark[1]},${dark[2]}))`;
}

function getClassColor(cls){
const tmp=document.createElement("div");
tmp.className=cls;
tmp.style.display="none";
document.body.appendChild(tmp);
const c=getComputedStyle(tmp).backgroundColor;
document.body.removeChild(tmp);
return c.match(/\d+/g).map(Number);
}

const color1=getClassColor(class1);
const color2=getClassColor(class2);

function animateGradient(from,to,time,cb){
const start=performance.now();

function frame(now){
let t=(now-start)/time;
if(t>1) t=1;

const rgb=[
Math.round(from[0]+(to[0]-from[0])*t),
Math.round(from[1]+(to[1]-from[1])*t),
Math.round(from[2]+(to[2]-from[2])*t)
];

wordContainer.style.background=gradientFrom(rgb);

if(t<1) requestAnimationFrame(frame);
else if(cb) cb();
}

requestAnimationFrame(frame);
}

function scaleAll(v){
charSpans.forEach(s=>s.style.transform=`scale(${v})`);
}

function animateScale(_span,from,to,time,cb){
const start=performance.now();

function frame(now){
let t=(now-start)/time;
if(t>1) t=1;

const eased=easeOutBack(t);
const val=from+(to-from)*eased;
_span.style.transform=`scale(${val})`;

if(t<1) requestAnimationFrame(frame);
else if(cb) cb();
}

requestAnimationFrame(frame);
}

// ---------- SEQUENCE ----------

wordContainer.style.background=gradientFrom(color1);

// pulse
animateGradient(color1,[255,255,255],duration);
charSpans.forEach(s=>animateScale(s,1,1.5,duration));

setTimeout(()=>{
animateGradient([255,255,255],color1,duration);
charSpans.forEach(s=>animateScale(s,1.5,1,duration));
},duration);

// letter wave
setTimeout(()=>{

let i=0;

function next(){
if(i>=charSpans.length){
swapClasses();
return;
}

animateScale(charSpans[i],1,1.5,duration,()=>{
animateScale(charSpans[i],1.5,1,duration);
});

i++;
setTimeout(next,duration);
}

next();

},duration*2);

// swap classes
function swapClasses(){
let count=0;
let state=false;

function step(){
if(count>=4){
showTeam();
return;
}

state=!state;
animateGradient(
state?color1:color2,
state?color2:color1,
0
);

count++;
setTimeout(step,duration);
}

step();
}

// team
function showTeam(){
//     let charBoxes = document.querySelectorAll('.charBox');
//     charBoxes.forEach(box => {
//         box.style.visibility = 'hidden';
//         box.style.width = 0;
//         box.style.height = 0;
//     });
wordContainer.innerHTML="";

const team=document.createElement("div");
team.textContent=(teamName14||"").toUpperCase().slice(0,14);
team.style.fontSize=teamFont+"px";
team.style.display="flex";
team.style.alignItems="center";
team.style.justifyContent="center";
team.style.height=cellSize+"px";
team.style.width="100%";

wordContainer.appendChild(team);

animateRandomBackground();
}

// random bg
function animateRandomBackground(){
let count=0;

function step(){
const base=color1;
const rand=base.map(v=>
Math.max(0,Math.min(255,
v+(Math.random()*0.6-0.3)*255
))
);

animateGradient(base,rand,duration);

count++;
if(count<4) setTimeout(step,duration);
else finish();
}

step();
}

// finish
function finish(){
wordContainer.style.opacity="0";
setTimeout(()=>{
container.innerHTML="";
if(elementToHide) elementToHide.style.visibility="";
},duration);
}

}