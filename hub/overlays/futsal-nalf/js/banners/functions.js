function startLikeSubBellAnimation()
{gsap.set("#like", { x: 63, y: 36, transformOrigin: "center" });
gsap.set("#subscribe", { x: 204, y: 36, transformOrigin: "center" });
gsap.set("#bell", { x: 411, y: 36, transformOrigin: "center" });
gsap.set("#bell-clicked", { transformOrigin: "center" });

gsap.set("#arrow", {
  x: 20,
  y: 195,
  opacity: 0,
  transformOrigin: "center"
});



const tl = gsap.timeline({
  repeat: 0,

});

tl.to("#arrow", {
  y: 85,
  opacity: 1,
  duration: 0.5,
  delay:2,
  ease: "power2.out"
})

.add(clickElement("#like"))

.to("#arrow", {
  x: 200,
  duration: 0.7,
  ease: "power2.inOut"
})

.add(clickElement("#subscribe"))

.to("#arrow", {
  x: 370,
  duration: 0.7,
  ease: "power2.inOut"
})

.add(clickElement("#bell"))

.to("#bell-clicked", {
  rotation: 15,
  duration: 0.08,
  yoyo: true,
  repeat: 5
})

.to("#arrow", {
  y: 125,
  opacity: 0,
  duration: 0.4
});
}

function clickElement(selector) {
  const tl = gsap.timeline({delay:2});

  tl.to(`${selector} .normal`, {
    opacity: 0,
    duration: 0.12
  })
  .to(`${selector} .clicked`, {
    opacity: 1,
    duration: 0.12
  }, "<")
  .to(selector, {
    scale: 1.15,
    duration: 0.12,
    yoyo: true,
    repeat: 1
  });

  return tl;
}

function startNalfSocialsAnimation(){

gsap.set(".item", {
  y: 120,
  opacity: 0
});

const items = [".item1", ".item2", ".item3", ".item4"];
const tl = gsap.timeline({ repeat: 0, delay:2});

items.forEach((item, index) => {
  const nextItem = items[(index + 1) % items.length];

  tl.to(item, {
    y: 0,
    opacity: 1,
    duration: 0.6,
    ease: "power2.out"
  })

  .to({}, { duration: 5 })

  .to(item, {
    y: -120,
    opacity: 0,
    duration: 0.6,
    ease: "power2.in"
  })

  .set(item, {
    y: 120
  });
});
}