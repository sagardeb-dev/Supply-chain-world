// Stylised 3D map of the Asia-Europe lane. Everything the scene shows is
// derived from observations only (counts, pipeline, bulletin level) — the
// hidden state never reaches this module, mirroring the POMDP boundary.
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { CSS2DRenderer, CSS2DObject } from 'three/addons/renderers/CSS2DRenderer.js';

// ---- map geometry (x: west<0<east, z: north<0<south) ----------------------
const PORT_ASIA = [85, 6];
const PORT_EU = [-76, -10];
// factor 2: two supplier nodes inland (east) of the origin port, each
// feeding Shanghai. Qualified above, spot below.
const SUP_QUALIFIED = [108, -6];
const SUP_SPOT = [108, 18];
const PT_BAB = [27, 26];
const PT_CANAL = [7, 7];
const PT_CAPE = [-22, 66];

const SUEZ_PTS = [PORT_ASIA, [62, 18], [44, 25], PT_BAB, [16, 16], PT_CANAL,
  [-6, 1], [-30, -3], [-56, -7], PORT_EU];
const CAPE_PTS = [PORT_ASIA, [58, 28], [32, 44], [2, 57], PT_CAPE,
  [-48, 49], [-62, 28], [-68, 6], PORT_EU];
const DIVERT_PTS = [PT_CANAL, [16, 16], PT_BAB, [24, 40], [2, 57], PT_CAPE,
  [-48, 49], [-62, 28], [-68, 6], PORT_EU];
const DIVERT_WEEKS = 3; // cfg.divert_extra_weeks — eta is fixed at divert time

const EURASIA = [[-100, -75], [100, -75], [100, 2], [70, 0], [55, -2], [46, 3],
  [40, 9], [36, 15], [32, 22], [26, 22], [21, 15], [15, 9], [10, 4], [3, 1],
  [-8, -4], [-32, -7], [-58, -11], [-72, -12], [-84, -12], [-100, -24]];
const AFRICA = [[-58, 14], [-30, 6], [-6, 6], [4, 9], [10, 13], [15, 21],
  [22, 28], [20, 38], [8, 48], [-6, 55], [-18, 61], [-32, 52], [-46, 38], [-54, 24]];

// Calm-week baselines from REGIME_COUNTS — used only to colour-grade the
// observed counts (green/amber/red), not to infer anything hidden.
const BASELINE = { suez: 70, bab: 70, cape: 60 };

const COL = {
  suez: 0x2dd4bf, cape: 0xf59e0b,
  ok: 0x4ade80, warn: 0xf59e0b, alert: 0xf87171,
  land: 0x16243a, ocean: 0x081c33, ship: 0xe8eef7,
};

function curveFrom(pts, y = 0.7) {
  return new THREE.CatmullRomCurve3(
    pts.map(([x, z]) => new THREE.Vector3(x, y, z)), false, 'catmullrom', 0.15);
}

function landMesh(pts) {
  const shape = new THREE.Shape(pts.map(([x, z]) => new THREE.Vector2(x, -z)));
  const geo = new THREE.ExtrudeGeometry(shape, { depth: 2.2, bevelEnabled: true, bevelSize: 0.8, bevelThickness: 0.6, bevelSegments: 2 });
  geo.rotateX(-Math.PI / 2);
  const mesh = new THREE.Mesh(geo, new THREE.MeshStandardMaterial({
    color: COL.land, roughness: 0.9, metalness: 0.05,
  }));
  mesh.position.y = -0.4;
  return mesh;
}

function makeLabel(cls) {
  const el = document.createElement('div');
  el.className = cls;
  return new CSS2DObject(el);
}

function buildShip(qty) {
  const g = new THREE.Group();
  const hull = new THREE.Mesh(
    new THREE.BoxGeometry(4.2, 0.9, 1.5),
    new THREE.MeshStandardMaterial({ color: 0x32465f, roughness: 0.6 }));
  hull.position.y = 0.45;
  g.add(hull);
  const bridge = new THREE.Mesh(
    new THREE.BoxGeometry(0.7, 1.0, 1.1),
    new THREE.MeshStandardMaterial({ color: COL.ship, roughness: 0.4 }));
  bridge.position.set(-1.5, 1.4, 0);
  g.add(bridge);
  const stacks = qty / 20; // one container stack per 20 units
  for (let i = 0; i < stacks; i++) {
    const c = new THREE.Mesh(
      new THREE.BoxGeometry(1.2, 0.8, 1.1),
      new THREE.MeshStandardMaterial({ color: i ? COL.cape : COL.suez, roughness: 0.5 }));
    c.position.set(0.2 + i * 1.4, 1.3, 0);
    g.add(c);
  }
  return g;
}

// Animated traffic along a lane: dot density tracks the observed weekly count.
class LaneFlow {
  constructor(curve, color, max = 40) {
    this.curve = curve;
    this.max = max;
    this.visible = 0;
    this.target = 0;
    this.offsets = Array.from({ length: max }, () => Math.random());
    this.speeds = Array.from({ length: max }, () => 0.012 + Math.random() * 0.01);
    this.mesh = new THREE.InstancedMesh(
      new THREE.SphereGeometry(0.5, 6, 6),
      new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.8 }),
      max);
    this.mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
    this.dummy = new THREE.Object3D();
  }

  setCount(weeklyCount) {
    this.target = Math.min(this.max, Math.round(weeklyCount / 2));
  }

  update(t, dt) {
    // ease the dot population toward the observed count
    this.visible += (this.target - this.visible) * Math.min(1, dt * 2.5);
    const n = Math.round(this.visible);
    for (let i = 0; i < this.max; i++) {
      if (i < n) {
        const u = (this.offsets[i] + t * this.speeds[i]) % 1;
        const p = this.curve.getPointAt(u);
        this.dummy.position.copy(p);
        this.dummy.scale.setScalar(1);
      } else {
        this.dummy.scale.setScalar(0.0001);
      }
      this.dummy.updateMatrix();
      this.mesh.setMatrixAt(i, this.dummy.matrix);
    }
    this.mesh.instanceMatrix.needsUpdate = true;
  }
}

// A chokepoint: pulsing ring + count label, colour-graded vs calm baseline.
class Chokepoint {
  constructor(scene, [x, z], baseline) {
    this.baseline = baseline;
    this.ratio = 1;
    this.ring = new THREE.Mesh(
      new THREE.TorusGeometry(2.6, 0.28, 10, 40),
      new THREE.MeshBasicMaterial({ color: COL.ok, transparent: true, opacity: 0.9 }));
    this.ring.rotation.x = Math.PI / 2;
    this.ring.position.set(x, 0.5, z);
    scene.add(this.ring);

    this.label = makeLabel('map-label');
    this.label.position.set(x, 5.5, z);
    scene.add(this.label);
  }

  set(name, count) {
    this.ratio = count / this.baseline;
    const level = this.ratio <= 0.05 ? 'alert' : this.ratio < 0.6 ? 'alert'
      : this.ratio < 0.95 ? 'warn' : 'ok';
    this.ring.material.color.set(COL[level === 'ok' ? 'ok' : level]);
    this.label.element.className = `map-label ${level === 'ok' ? '' : level}`;
    this.label.element.innerHTML = `${name}<b>${count}</b>`;
  }

  update(t) {
    // pulse harder the further counts fall below baseline
    const distress = Math.max(0, 1 - this.ratio);
    const s = 1 + Math.sin(t * (2 + distress * 6)) * 0.08 * (0.5 + distress);
    this.ring.scale.setScalar(s);
  }
}

export class SceneView {
  constructor(container) {
    this.scene = new THREE.Scene();
    this.scene.fog = new THREE.Fog(0x060d18, 180, 420);

    this.camera = new THREE.PerspectiveCamera(50, 1, 1, 1000);
    this.camera.position.set(0, 120, 118);

    this.renderer = new THREE.WebGLRenderer({ antialias: true });
    this.renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    this.renderer.setClearColor(0x060d18);
    container.appendChild(this.renderer.domElement);

    this.labelRenderer = new CSS2DRenderer();
    Object.assign(this.labelRenderer.domElement.style,
      { position: 'absolute', top: '0', pointerEvents: 'none' });
    container.appendChild(this.labelRenderer.domElement);

    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.target.set(0, 0, 14);
    this.controls.maxPolarAngle = Math.PI * 0.46;
    this.controls.minDistance = 50;
    this.controls.maxDistance = 320;
    this.controls.enableDamping = true;

    this.scene.add(new THREE.AmbientLight(0x8fb3e0, 0.7));
    const sun = new THREE.DirectionalLight(0xfff4e0, 1.4);
    sun.position.set(-60, 120, -40);
    this.scene.add(sun);

    // ocean + land
    const ocean = new THREE.Mesh(
      new THREE.PlaneGeometry(420, 320),
      new THREE.MeshStandardMaterial({ color: COL.ocean, roughness: 0.75, metalness: 0.25 }));
    ocean.rotation.x = -Math.PI / 2;
    ocean.position.set(0, -0.6, 10);
    this.scene.add(ocean);
    this.scene.add(landMesh(EURASIA));
    this.scene.add(landMesh(AFRICA));

    // routes
    this.curves = {
      suez: curveFrom(SUEZ_PTS),
      cape: curveFrom(CAPE_PTS),
      divert: curveFrom(DIVERT_PTS),
    };
    this.scene.add(this.tube(this.curves.suez, COL.suez));
    this.scene.add(this.tube(this.curves.cape, COL.cape));

    // canal point on the suez curve, for pinning queued ships
    this.canalPos = new THREE.Vector3(PT_CANAL[0], 0.7, PT_CANAL[1]);

    // chokepoints + ports
    this.cp = {
      suez: new Chokepoint(this.scene, PT_CANAL, BASELINE.suez),
      bab: new Chokepoint(this.scene, PT_BAB, BASELINE.bab),
      cape: new Chokepoint(this.scene, PT_CAPE, BASELINE.cape),
    };
    this.addPort(PORT_ASIA);
    this.addPort(PORT_EU);
    this.portLabels = {
      origin: this.anchorLabel(PORT_ASIA, 'map-label port'),
      dest: this.anchorLabel(PORT_EU, 'map-label port'),
    };

    // blockage barrier — shown only when the observed suez count hits 0
    this.barrier = new THREE.Mesh(
      new THREE.BoxGeometry(7, 1.6, 1.2),
      new THREE.MeshBasicMaterial({ color: COL.alert }));
    this.barrier.position.set(PT_CANAL[0], 1.0, PT_CANAL[1]);
    this.barrier.rotation.y = Math.PI / 4;
    this.barrier.visible = false;
    this.scene.add(this.barrier);

    // traffic
    this.flows = {
      suez: new LaneFlow(this.curves.suez, COL.suez),
      cape: new LaneFlow(this.curves.cape, COL.cape),
    };
    this.scene.add(this.flows.suez.mesh, this.flows.cape.mesh);

    // factor 2: upstream supplier stage — two nodes + short feeder lanes
    // into the origin port. Feeder density encodes the shipped fraction;
    // the chosen supplier's lane lights, the other dims (set in applyObs).
    this.supCurves = {
      qualified: curveFrom([SUP_QUALIFIED, [97, 0], PORT_ASIA], 0.7),
      spot: curveFrom([SUP_SPOT, [97, 12], PORT_ASIA], 0.7),
    };
    this.scene.add(this.tube(this.supCurves.qualified, COL.suez));
    this.scene.add(this.tube(this.supCurves.spot, COL.cape));
    this.feeders = {
      qualified: new LaneFlow(this.supCurves.qualified, COL.suez, 14),
      spot: new LaneFlow(this.supCurves.spot, COL.cape, 14),
    };
    this.scene.add(this.feeders.qualified.mesh, this.feeders.spot.mesh);
    this.addPort(SUP_QUALIFIED);
    this.addPort(SUP_SPOT);
    this.supLabels = {
      qualified: this.anchorLabel(SUP_QUALIFIED, 'map-label sup'),
      spot: this.anchorLabel(SUP_SPOT, 'map-label sup'),
    };

    // player shipments, keyed by dispatched week (one order per week)
    this.ships = new Map();
    this.displayWeek = 0;
    this.tween = null;
    this.labels = null;
    this.lastCounts = { suez: BASELINE.suez, bab: BASELINE.bab, cape: BASELINE.cape };

    this.clock = new THREE.Clock();
    this.resize(container);
    new ResizeObserver(() => this.resize(container)).observe(container);
    this.renderer.setAnimationLoop(() => this.frame());
  }

  tube(curve, color) {
    return new THREE.Mesh(
      new THREE.TubeGeometry(curve, 120, 0.22, 6),
      new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.28 }));
  }

  addPort([x, z]) {
    const pad = new THREE.Mesh(
      new THREE.CylinderGeometry(2.2, 2.2, 0.7, 24),
      new THREE.MeshStandardMaterial({ color: 0x3a527a, roughness: 0.6 }));
    pad.position.set(x, 0.3, z);
    this.scene.add(pad);
  }

  anchorLabel([x, z], cls) {
    const l = makeLabel(cls);
    l.position.set(x, 3.4, z);
    this.scene.add(l);
    return l;
  }

  resize(container) {
    const { clientWidth: w, clientHeight: h } = container;
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(w, h);
    this.labelRenderer.setSize(w, h);
  }

  setLabels(labels) {
    this.labels = labels;
    this.portLabels.origin.element.textContent = labels.origin;
    this.portLabels.dest.element.textContent = labels.dest;
    if (this.supLabels) {
      this.supLabels.qualified.element.textContent = labels.supQualified;
      this.supLabels.spot.element.textContent = labels.supSpot;
    }
  }

  // Light the chosen supplier's feeder at a density proportional to the
  // shipped qty (degraded spot ships short -> a thin/stuttering feeder);
  // the unchosen feeder idles. obs.sourcing is null when nothing shipped.
  _driveFeeders(obs) {
    if (!this.feeders) return;
    const chosen = obs.sourcing?.supplier ?? null;
    const shipped = obs.sourcing?.shipped ?? 0;
    for (const id of ['qualified', 'spot']) {
      const lit = id === chosen;
      // density: ~2 dots per shipped unit on the chosen lane, idle otherwise
      this.feeders[id].setCount(lit ? Math.max(2, shipped) : 0);
      this.feeders[id].mesh.material.opacity = lit ? 0.9 : 0.18;
    }
  }

  reset(obs) {
    for (const s of this.ships.values()) this.removeShip(s);
    this.ships.clear();
    this.displayWeek = 0;
    this.tween = null;
    this.applyObs(obs, { animate: false });
  }

  // Sync the scene to a new observation. With animate=true the week
  // counter tweens, sailing every ship forward over ~1.4 s.
  applyObs(obs, { animate = true } = {}) {
    this.lastCounts = { suez: obs.suezCount, bab: obs.babCount, cape: obs.capeCount };
    this.cp.suez.set(this.labels.suez, obs.suezCount);
    this.cp.bab.set(this.labels.bab, obs.babCount);
    this.cp.cape.set(this.labels.cape, obs.capeCount);
    this.flows.suez.setCount(obs.suezCount);
    this.flows.cape.setCount(obs.capeCount);
    this.barrier.visible = obs.suezCount === 0;
    this._driveFeeders(obs);

    const seen = new Set();
    for (const s of obs.pipeline) {
      seen.add(s.dispatched);
      const existing = this.ships.get(s.dispatched);
      if (existing) {
        existing.data = s;
      } else {
        const mesh = buildShip(s.qty);
        const tag = makeLabel('ship-label');
        tag.element.textContent = s.qty;
        tag.position.y = 3;
        mesh.add(tag);
        this.scene.add(mesh);
        this.ships.set(s.dispatched, { mesh, data: s, landing: false });
      }
    }
    // ships gone from the pipeline have landed: let them sail to port,
    // then remove them when the week tween passes their eta
    for (const [key, ship] of this.ships) {
      if (!seen.has(key)) ship.landing = true;
    }

    if (animate) {
      this.tween = { from: this.displayWeek, to: obs.week, t: 0 };
    } else {
      this.displayWeek = obs.week;
    }
  }

  removeShip(ship) {
    ship.mesh.traverse((o) => o.isCSS2DObject && o.removeFromParent());
    this.scene.remove(ship.mesh);
  }

  shipPosition(ship, week, out, tangent) {
    const { data } = ship;
    if (data.status === 'queued') {
      out.copy(this.canalPos);
      out.x += 2.5; out.z += 2.5; // anchored at the southern approach
      tangent.set(-1, 0, -1).normalize();
      return;
    }
    let curve = this.curves[data.route];
    let t;
    if (data.status === 'diverted') {
      curve = this.curves.divert;
      const divertedAt = data.eta - DIVERT_WEEKS;
      t = (week - divertedAt) / DIVERT_WEEKS;
      if (t < 0) { // still showing the pre-divert queue during the tween
        out.copy(this.canalPos);
        tangent.set(-1, 0, -1).normalize();
        return;
      }
    } else {
      t = (week - data.dispatched) / (data.eta - data.dispatched);
    }
    t = THREE.MathUtils.clamp(t, 0.001, 0.999);
    curve.getPointAt(t, out);
    curve.getTangentAt(t, tangent);
  }

  frame() {
    const dt = this.clock.getDelta();
    const t = this.clock.elapsedTime;

    if (this.tween) {
      this.tween.t = Math.min(1, this.tween.t + dt / 1.4);
      const e = 1 - (1 - this.tween.t) ** 3; // ease-out cubic
      this.displayWeek = this.tween.from + (this.tween.to - this.tween.from) * e;
      if (this.tween.t >= 1) this.tween = null;
    }

    const pos = new THREE.Vector3();
    const tan = new THREE.Vector3();
    for (const [key, ship] of this.ships) {
      this.shipPosition(ship, this.displayWeek, pos, tan);
      pos.y += Math.sin(t * 2 + key) * 0.15; // bob
      ship.mesh.position.copy(pos);
      ship.mesh.lookAt(pos.x + tan.x, pos.y, pos.z + tan.z);
      if (ship.landing && this.displayWeek >= ship.data.eta - 0.05) {
        this.removeShip(ship);
        this.ships.delete(key);
        continue;
      }
      // amber distress blink on the hull while waiting at the canal
      const hullMat = ship.mesh.children[0].material;
      if (ship.data.status === 'queued') {
        const blink = (Math.sin(t * 6) + 1) / 2;
        hullMat.emissive.setHex(0x885500).multiplyScalar(blink);
      } else {
        hullMat.emissive.setHex(0x000000);
      }
    }

    this.flows.suez.update(t, dt);
    this.flows.cape.update(t, dt);
    if (this.feeders) {
      this.feeders.qualified.update(t, dt);
      this.feeders.spot.update(t, dt);
    }
    for (const cp of Object.values(this.cp)) cp.update(t);

    this.controls.update();
    this.renderer.render(this.scene, this.camera);
    this.labelRenderer.render(this.scene, this.camera);
  }

  get animating() { return this.tween !== null; }
}
