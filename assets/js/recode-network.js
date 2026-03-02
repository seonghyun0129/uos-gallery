(() => {
  const dataPath = "/assets/data/network-catalog.json";
  const SHOW_MOCKS_STORAGE_KEY = "recode-network-show-mocks";
  const stage = document.getElementById("network-stage");
  const host = document.getElementById("network-canvas");
  const infoBox = document.getElementById("network-selected");
  const mockCheckbox = document.getElementById("network-show-mock");
  const queryParams = new URLSearchParams(window.location.search);
  const pageConfig = (typeof window.RECODE_NETWORK_OPTIONS === "object" && window.RECODE_NETWORK_OPTIONS !== null)
    ? window.RECODE_NETWORK_OPTIONS
    : {};
  const NODE_STYLE = String(
    queryParams.get("nodeStyle") || queryParams.get("style") || pageConfig.nodeStyle || "thumbnail"
  ).toLowerCase();
  const SHOW_MINIMAL_UI = pageConfig.showMinimalUi !== false;

  if (!stage || !host || !window.THREE) {
    return;
  }

  const NODE_SIZE = 88;
  const BASE_RADIUS = 470;
  const DEPTH_SPREAD = 220;
  const DRIFT_X = 11;
  const DRIFT_Y = 8;
  const DRIFT_Z = 14;
  const CAMERA_Z = 760;
  const AUTO_ROTATE = 0.0007;
  const FORCE_NO_THUMB = (NODE_STYLE === "no-thumb" || NODE_STYLE === "no-thumbnail" || NODE_STYLE === "text");
  const HOVER_SCALE = FORCE_NO_THUMB ? 1.16 : 1.22;
  const NODE_CLUSTER_RADIUS = BASE_RADIUS;
  const NODE_CLUSTER_DEPTH = DEPTH_SPREAD;
  const NO_THUMB_NODE_WIDTH = NODE_SIZE * 2.05;
  const NO_THUMB_NODE_HEIGHT = NODE_SIZE * 0.72;
  if (FORCE_NO_THUMB && SHOW_MINIMAL_UI && document.body) {
    document.body.classList.add("no-thumb-mode");
  }

  const scene = new THREE.Scene();
  const clusterGroup = new THREE.Group();
  scene.add(clusterGroup);

  const camera = new THREE.PerspectiveCamera(44, 1, 0.1, 3000);
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  if (FORCE_NO_THUMB) {
    scene.background = null;
    renderer.setClearColor(0x000000, 0);
  }
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  host.appendChild(renderer.domElement);

  const raycaster = new THREE.Raycaster();
  const pointer = new THREE.Vector2();
  const orbit = { x: 0, y: 0, targetX: 0, targetY: 0, rot: 0 };
  const drag = { active: false, x: 0, y: 0 };
  const lastPointer = { x: -9999, y: -9999, active: false };

  let width = 0;
  let height = 0;

  let nodes = [];
  let meshes = [];
  let hoveredMesh = null;
  let entered = false;
  let spreadProgress = 0;
  let cameraZ = CAMERA_Z;
  let entryGate = null;
  let cachedPayload = null;
  let loadToken = 0;
  let listenersBound = false;

  function compactText(value, maxLength) {
    const text = String(value || "").replace(/\s+/g, " ").trim();
    if (!text) return "";
    if (text.length <= maxLength) return text;
    return `${text.slice(0, maxLength)}...`;
  }

  function hashText(seedText) {
    let hash = 0;
    const text = String(seedText || "");
    for (let i = 0; i < text.length; i += 1) {
      hash = (hash << 5) - hash + text.charCodeAt(i);
      hash |= 0;
    }
    return Math.abs(hash);
  }

  function makeRelId(item) {
    const base = `${item.id || ""}-${item.artistSlug || ""}-${item.title || ""}`;
    return hashText(base).toString(16).slice(0, 6).padStart(6, "0").toUpperCase();
  }

  function shouldShowMocks() {
    const mockQuery = queryParams.get("mock");
    if (mockQuery !== null) {
      const normalized = mockQuery.toLowerCase();
      return normalized === "1" || normalized === "true" || normalized === "on" || normalized === "yes";
    }
    return window.localStorage?.getItem(SHOW_MOCKS_STORAGE_KEY) === "1";
  }

  function shouldUseThumbnails() {
    return NODE_STYLE !== "no-thumb" && NODE_STYLE !== "no-thumbnail" && NODE_STYLE !== "text";
  }

  function keepMockQueryInUrl(nextValue) {
    const url = new URL(window.location.href);
    if (nextValue) {
      url.searchParams.set("mock", "1");
    } else {
      url.searchParams.delete("mock");
    }
    window.history.replaceState({}, "", url);
  }

  function resetNetworkState() {
    entered = false;
    spreadProgress = 0;
    orbit.x = 0;
    orbit.y = 0;
    orbit.targetX = 0;
    orbit.targetY = 0;
    orbit.rot = 0;
    cameraZ = CAMERA_Z;
    setNodeHighlighted(null);
    if (entryGate) {
      entryGate.remove();
      entryGate = null;
    }
  }

  function bindStageEvents() {
    if (listenersBound) return;

    stage.addEventListener("pointermove", onPointerMove);
    stage.addEventListener("pointerdown", onPointerDown);
    stage.addEventListener("pointerup", onPointerUp);
    stage.addEventListener("pointerleave", onPointerLeave);
    stage.addEventListener("wheel", onWheel, { passive: false });
    window.addEventListener("resize", resize);
    listenersBound = true;
  }

  async function loadCatalogPayload() {
    if (cachedPayload) return cachedPayload;
    const response = await fetch(dataPath, { cache: "no-store" });
    if (!response.ok) {
      throw new Error("network data unavailable");
    }
    cachedPayload = await response.json();
    return cachedPayload;
  }

  async function renderNetwork(includeMock) {
    const token = ++loadToken;

    const payload = await loadCatalogPayload();
    if (token !== loadToken) return;

    const items = getItems(payload, includeMock);
    if (!items.length) {
      renderError("현재 표시할 항목이 없습니다.");
      return;
    }

    const graphNodes = items.map((item, index) => ({ ...item, id: item.id || `item-${index}` }));
    resetNetworkState();
    await createNodes(graphNodes);
    if (token !== loadToken) return;

    if (infoBox) {
      infoBox.textContent = `선택: 총 ${graphNodes.length}개${includeMock ? " (목업 포함)" : ""}`;
    }
    resize();
    bindStageEvents();
    entryGate = createEntryGate();
  }

  function getItems(payload, includeMocks) {
    const realItems = Array.isArray(payload?.items) ? payload.items : [];
    if (includeMocks) {
      const mockItems = Array.isArray(payload?.mockItems) ? payload.mockItems : [];
      const included = mockItems
        .filter((item) => item && item.isMock !== false)
        .map((item) => ({ ...item, isMock: true }));
      return [...realItems, ...included];
    }
    return realItems
      .filter((item) => item && item.isMock !== true)
      .map((item) => ({ ...item, isMock: false }));
  }

  function setupMockToggle(showMock) {
    if (!mockCheckbox) return;
    mockCheckbox.checked = !!showMock;

    mockCheckbox.addEventListener("change", async () => {
      const nextValue = mockCheckbox.checked;
      window.localStorage?.setItem(SHOW_MOCKS_STORAGE_KEY, nextValue ? "1" : "0");
      keepMockQueryInUrl(nextValue);
      await renderNetwork(nextValue);
    });
  }

  function renderError(message) {
    host.textContent = "";
    const fallback = document.createElement("p");
    fallback.className = "network-empty";
    fallback.textContent = message;
    host.appendChild(fallback);
  }

  function setSelected(work) {
    if (!infoBox) return;
    if (!work) {
      infoBox.textContent = "선택: 없음";
      return;
    }
    const title = work.title || "Untitled";
    const artist = work.artist || work.artistSlug || "Unknown";
    const ym = [work.year, work.month].filter(Boolean).join(".");
    const mockText = work.isMock ? " · MOCK" : "";
    infoBox.textContent = `선택: ${title} · ${artist}${ym ? " · " + ym : ""}${mockText}`;
  }

  function getNodeImagePath(work) {
    if (!shouldUseThumbnails()) {
      return "";
    }
    return (
      work.thumbnail ||
      work.image ||
      work.imagePath ||
      work.thumbnailPath ||
      work.image_url ||
      work.img ||
      ""
    );
  }

  function loadNodeImage(src) {
    return new Promise((resolve) => {
      if (!src) {
        resolve(null);
        return;
      }

      const img = new Image();
      img.decoding = "async";
      img.crossOrigin = "anonymous";
      img.onload = () => resolve(img);
      img.onerror = () => resolve(null);
      img.src = src;
    });
  }

  function roundRectPath(ctx, x, y, w, h, r) {
    const radius = Math.max(0, Math.min(r, w / 2, h / 2));
    if (ctx.roundRect) {
      ctx.roundRect(x, y, w, h, radius);
      return;
    }

    const rr = radius;
    ctx.moveTo(x + rr, y);
    ctx.lineTo(x + w - rr, y);
    ctx.quadraticCurveTo(x + w, y, x + w, y + rr);
    ctx.lineTo(x + w, y + h - rr);
    ctx.quadraticCurveTo(x + w, y + h, x + w - rr, y + h);
    ctx.lineTo(x + rr, y + h);
    ctx.quadraticCurveTo(x, y + h, x, y + h - rr);
    ctx.lineTo(x, y + rr);
    ctx.quadraticCurveTo(x, y, x + rr, y);
  }

  function drawNoThumbFallback(ctx, width, height, work, isMock, isActive) {
    const panel = work.__panel || {};
    const archiveCode = String(panel.archiveCode || "000").padStart(3, "0");
    const relId = String(panel.relId || makeRelId(work).slice(0, 5)).toLowerCase();
    const line1 = `> ARCHIVE_DATA_${archiveCode}`;
    const line2 = `REL_ID: ${relId}`;
    const line3 = compactText(`${work.artist || work.artistSlug || "Unknown"} - ${work.title || "Untitled"}`, 34);
    const textColor = isActive ? "#000000" : (isMock ? "#ffef9a" : "#00ff79");
    const line3Color = isActive ? "rgba(0, 0, 0, 0.8)" : "rgba(163, 255, 197, 0.82)";
    const outerStroke = isActive ? "#00ff41" : "rgba(52, 255, 143, 0.24)";
    const rect = {
      x: width * 0.05,
      y: height * 0.19,
      w: width * 0.9,
      h: height * 0.62,
      r: 4,
    };

    ctx.save();

    if (isActive) {
      ctx.shadowColor = "rgba(0, 255, 65, 0.85)";
      ctx.shadowBlur = 28;
      ctx.fillStyle = "#00ff41";
      ctx.beginPath();
      roundRectPath(ctx, rect.x + 1, rect.y + 1, rect.w - 2, rect.h - 2, rect.r);
      ctx.fill();
      ctx.shadowBlur = 0;
    }

    ctx.strokeStyle = outerStroke;
    ctx.lineWidth = isActive ? 1.8 : 1.4;
    ctx.beginPath();
    roundRectPath(ctx, rect.x + 1, rect.y + 1, rect.w - 2, rect.h - 2, rect.r);
    ctx.stroke();

    ctx.fillStyle = textColor;
    ctx.textAlign = "left";
    ctx.textBaseline = "middle";
    ctx.font = `700 ${Math.round(height * 0.17)}px "Courier New", monospace`;
    ctx.fillText(line1, rect.x + 14, rect.y + rect.h * 0.4);

    ctx.font = `600 ${Math.round(height * 0.11)}px "Courier New", monospace`;
    ctx.fillText(line2, rect.x + 14, rect.y + rect.h * 0.66);

    ctx.font = `400 ${Math.round(height * 0.09)}px "Courier New", monospace`;
    ctx.fillStyle = line3Color;
    ctx.fillText(line3, rect.x + 14, rect.y + rect.h - 14);

    ctx.restore();
  }

  function makeNodeTexture(work, image, options = {}) {
    const isActive = !!options.active;
    const useNoThumbStyle = FORCE_NO_THUMB;
    const canvasWidth = useNoThumbStyle ? 720 : 256;
    const canvasHeight = useNoThumbStyle ? 256 : 256;
    const canvas = document.createElement("canvas");
    canvas.width = canvasWidth;
    canvas.height = canvasHeight;
    const ctx = canvas.getContext("2d");
    if (!ctx) return new THREE.CanvasTexture(canvas);

    const isMock = !!work.isMock;
    const center = canvasWidth / 2;
    const radius = Math.min(canvasWidth, canvasHeight) * 0.44;
    const baseBg = isMock ? "rgba(24, 66, 35, 0.52)" : "rgba(8, 40, 18, 0.5)";
    const ringColor = isMock ? "rgba(255, 214, 102, 0.95)" : "rgba(57, 255, 170, 0.95)";
    const textColor = isMock ? "#ffe8a8" : "#c4ffd6";

    ctx.clearRect(0, 0, canvasWidth, canvasHeight);

    if (useNoThumbStyle) {
      drawNoThumbFallback(ctx, canvasWidth, canvasHeight, work, isMock, isActive);
    } else {
      const glow = ctx.createRadialGradient(center, center, radius * 0.2, center, center, radius + 6);
      glow.addColorStop(0, isMock ? "rgba(30, 100, 40, 0.5)" : "rgba(12, 74, 34, 0.5)");
      glow.addColorStop(1, isMock ? "rgba(8, 40, 18, 0.85)" : "rgba(7, 30, 14, 0.82)");
      ctx.fillStyle = glow;
      ctx.beginPath();
      ctx.arc(center, center, radius + 6, 0, Math.PI * 2);
      ctx.fill();

      ctx.fillStyle = baseBg;
      ctx.beginPath();
      ctx.arc(center, center, radius, 0, Math.PI * 2);
      ctx.fill();

      if (image) {
        ctx.save();
        ctx.beginPath();
        ctx.arc(center, center, radius - 2, 0, Math.PI * 2);
        ctx.clip();

        const iw = image.naturalWidth || image.width || 1;
        const ih = image.naturalHeight || image.height || 1;
        const scale = Math.max((radius * 2) / iw, (radius * 2) / ih);
        const dw = iw * scale;
        const dh = ih * scale;
        const dx = center - dw / 2;
        const dy = center - dh / 2;
        ctx.drawImage(image, dx, dy, dw, dh);
        ctx.restore();
      } else {
        const initial = compactText(work.artist || work.artistSlug || "U", 2).replace(/\s+/g, "");
        ctx.fillStyle = textColor;
        ctx.font = "bold 64px 'Courier New', monospace";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText((initial || "W").slice(0, 2), center, center);
      }

      ctx.beginPath();
      ctx.arc(center, center, radius - 2, 0, Math.PI * 2);
      ctx.strokeStyle = ringColor;
      ctx.lineWidth = 3;
      ctx.stroke();

      ctx.fillStyle = ringColor;
      ctx.font = "bold 18px 'Courier New', monospace";
      ctx.textAlign = "center";
      ctx.textBaseline = "top";
      ctx.fillText(compactText(`${work.artist || work.artistSlug || "Unknown"}`, 10), center, canvasHeight - 26);
    }

    const texture = new THREE.CanvasTexture(canvas);
    texture.colorSpace = THREE.SRGBColorSpace;
    texture.needsUpdate = true;
    return texture;
  }

  function setNodeHighlighted(mesh) {
    if (hoveredMesh === mesh) return;
    if (hoveredMesh) {
      const prev = hoveredMesh.userData.size || { width: NODE_SIZE, height: NODE_SIZE };
      const prevMaps = hoveredMesh.userData.maps;
      if (prevMaps?.normal && hoveredMesh.material.map !== prevMaps.normal) {
        hoveredMesh.material.map = prevMaps.normal;
        hoveredMesh.material.needsUpdate = true;
      }
      hoveredMesh.scale.set(prev.width, prev.height, 1);
      hoveredMesh.material.opacity = 0.9;
      hoveredMesh.renderOrder = 1;
    }

    hoveredMesh = mesh;
    if (hoveredMesh) {
      const next = hoveredMesh.userData.size || { width: NODE_SIZE, height: NODE_SIZE };
      const nextMaps = hoveredMesh.userData.maps;
      if (nextMaps?.active && hoveredMesh.material.map !== nextMaps.active) {
        hoveredMesh.material.map = nextMaps.active;
        hoveredMesh.material.needsUpdate = true;
      }
      hoveredMesh.scale.set(next.width * HOVER_SCALE, next.height * HOVER_SCALE, 1);
      hoveredMesh.material.opacity = 1;
      hoveredMesh.renderOrder = 30;
      setSelected(hoveredMesh.userData.work);
    } else {
      setSelected(null);
    }
  }

  function clearScene() {
    while (clusterGroup.children.length) {
      const child = clusterGroup.children[0];
      clusterGroup.remove(child);
      const altMaps = child.userData?.maps;
      if (altMaps) {
        Object.values(altMaps).forEach((mapTex) => {
          if (mapTex && mapTex !== child.material?.map) {
            mapTex.dispose();
          }
        });
      }
      if (child.material && child.material.map) {
        child.material.map.dispose();
      }
      if (child.material) {
        child.material.dispose();
      }
    }
    meshes = [];
    nodes = [];
    hoveredMesh = null;
  }

  async function createNodes(items) {
    clearScene();
    const goldenAngle = Math.PI * (3 - Math.sqrt(5));
    const nodeEntries = await Promise.all(items.map(async (item, index) => {
      const unit = (index + 0.5) / Math.max(items.length, 1);
      const radius = NODE_CLUSTER_RADIUS * Math.sqrt(unit);
      const angle = index * goldenAngle;

      const anchorX = Math.cos(angle) * radius;
      const anchorY = Math.sin(angle) * radius * 0.67;
      const anchorZ = (Math.random() - 0.5) * NODE_CLUSTER_DEPTH;
      const phase = Math.random() * Math.PI * 2;
      const enrichedItem = FORCE_NO_THUMB
        ? {
            ...item,
            __panel: {
              archiveCode: String((index + 1) % 1000).padStart(3, "0"),
              relId: makeRelId(item).slice(0, 5),
            },
          }
        : item;

      const thumbnail = getNodeImagePath(enrichedItem);
      const image = await loadNodeImage(thumbnail);
      const texture = makeNodeTexture(enrichedItem, image, { active: false });
      const activeTexture = FORCE_NO_THUMB ? makeNodeTexture(enrichedItem, image, { active: true }) : null;

      const material = new THREE.SpriteMaterial({
        map: texture,
        transparent: true,
        opacity: 0.9,
        depthTest: false,
        depthWrite: false,
      });
      const sprite = new THREE.Sprite(material);
      const isNoThumb = FORCE_NO_THUMB;
      const nodeWidth = isNoThumb ? NO_THUMB_NODE_WIDTH : NODE_SIZE;
      const nodeHeight = isNoThumb ? NO_THUMB_NODE_HEIGHT : NODE_SIZE;
      sprite.scale.set(nodeWidth, nodeHeight, 1);
      sprite.userData.size = { width: nodeWidth, height: nodeHeight };
      if (isNoThumb && activeTexture) {
        sprite.userData.maps = { normal: texture, active: activeTexture };
      }
      sprite.position.set(anchorX, anchorY, anchorZ);
      sprite.userData.work = enrichedItem;
      sprite.renderOrder = 1;

      return {
        mesh: sprite,
        anchorX,
        anchorY,
        anchorZ,
        phase,
      };
    }));

    nodeEntries.forEach((entry) => {
      clusterGroup.add(entry.mesh);
      meshes.push(entry.mesh);
      nodes.push(entry);
    });
  }

  function easeOutCubic(t) {
    return 1 - Math.pow(1 - t, 3);
  }

  function createEntryGate() {
    const gate = document.createElement("div");
    gate.id = "recode-entry-gate";
    gate.style.cssText = [
      "position:absolute", "inset:0", "display:flex", "flex-direction:column",
      "align-items:center", "justify-content:center", "gap:1rem",
      "cursor:pointer", "z-index:5", "user-select:none",
    ].join(";");

    const dot = document.createElement("div");
    dot.style.cssText = [
      "width:10px", "height:10px", "border-radius:50%",
      "background:#00ff41",
      "box-shadow:0 0 18px 6px rgba(0,255,65,0.6)",
      "animation:recode-gate-pulse 1.4s ease-in-out infinite",
    ].join(";");

    const label = document.createElement("div");
    label.textContent = "// CONNECT_TO_ARCHIVE";
    label.style.cssText = [
      "font-family:'Courier New',monospace", "font-size:0.85rem",
      "color:#00ff41", "letter-spacing:0.1em",
      "text-shadow:0 0 10px rgba(0,255,65,0.7)",
    ].join(";");

    if (!document.getElementById("recode-gate-style")) {
      const style = document.createElement("style");
      style.id = "recode-gate-style";
      style.textContent = `
        @keyframes recode-gate-pulse {
          0%,100%{opacity:1;transform:scale(1)}
          50%{opacity:0.4;transform:scale(1.5)}
        }
        #recode-entry-gate{transition:opacity 0.6s ease}
        #recode-entry-gate.hidden{opacity:0;pointer-events:none}
      `;
      document.head.appendChild(style);
    }

    gate.appendChild(dot);
    gate.appendChild(label);
    stage.appendChild(gate);
    return gate;
  }

  function resize() {
    const rect = stage.getBoundingClientRect();
    width = Math.max(rect.width, 320);
    height = Math.max(rect.height, 300);
    camera.aspect = width / height;
    camera.position.set(0, 0, cameraZ + Math.max(0, 1200 - width) * 0.08);
    camera.lookAt(0, 0, 0);
    camera.updateProjectionMatrix();
    renderer.setSize(width, height, false);
  }

  function onWheel(event) {
    event.preventDefault();
    cameraZ += event.deltaY * 0.5;
  }

  function pickNode(event) {
    const rect = renderer.domElement.getBoundingClientRect();
    pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
    pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
    raycaster.setFromCamera(pointer, camera);
    const intersections = raycaster.intersectObjects(meshes, false);
    if (!intersections.length) return null;
    return intersections[0].object;
  }

  function syncSelectionByPointer() {
    if (!lastPointer.active || drag.active) return;
    const picked = pickNode({ clientX: lastPointer.x, clientY: lastPointer.y });
    setNodeHighlighted(picked);
  }

  function onPointerMove(event) {
    if (event.target !== stage && !stage.contains(event.target)) return;
    lastPointer.active = true;
    lastPointer.x = event.clientX;
    lastPointer.y = event.clientY;

    const rect = renderer.domElement.getBoundingClientRect();
    const px = ((event.clientX - rect.left) / rect.width) * 2 - 1;
    const py = -((event.clientY - rect.top) / rect.height) * 2 + 1;
    orbit.targetX = px;
    orbit.targetY = py;

    if (!drag.active) {
      syncSelectionByPointer();
    }
  }

  function onPointerDown(event) {
    if (!entered) {
      entered = true;
      if (entryGate) {
        entryGate.classList.add("hidden");
        setTimeout(() => entryGate?.remove(), 700);
      }
      return;
    }
    drag.active = true;
    drag.x = event.clientX;
    drag.y = event.clientY;
    const picked = pickNode(event);
    setNodeHighlighted(picked);
  }

  function onPointerUp(event) {
    const moved = Math.hypot(event.clientX - drag.x, event.clientY - drag.y);
    const picked = pickNode(event);
    drag.active = false;

    if (moved < 5 && picked && picked.userData?.work?.path) {
      window.location.href = picked.userData.work.path;
    }
  }

  function onPointerLeave() {
    lastPointer.active = false;
    orbit.targetX = 0;
    orbit.targetY = 0;
    drag.active = false;
    setNodeHighlighted(null);
  }

  function animate(now) {
    requestAnimationFrame(animate);
    const time = (now || 0) * 0.001;
    const motionAmp = FORCE_NO_THUMB ? 0.34 : 1;
    const rotAmp = FORCE_NO_THUMB ? 0.4 : 1;

    if (entered && spreadProgress < 1) {
      spreadProgress = Math.min(1, spreadProgress + 0.016);
    }
    const eased = easeOutCubic(spreadProgress);

    camera.position.z = cameraZ + Math.max(0, 1200 - width) * 0.08;

    orbit.x += (orbit.targetX - orbit.x) * 0.07;
    orbit.y += (orbit.targetY - orbit.y) * 0.07;
    orbit.rot += AUTO_ROTATE * rotAmp;

    clusterGroup.rotation.y = orbit.x * (0.50 * rotAmp) + Math.sin(time * (0.12 * rotAmp)) * (0.03 * rotAmp);
    clusterGroup.rotation.x = -orbit.y * (0.35 * rotAmp) + Math.cos(time * (0.11 * rotAmp)) * (0.02 * rotAmp);

    for (const node of nodes) {
      const nx = node.anchorX * eased + Math.sin(time * 0.65 + node.phase) * (DRIFT_X * motionAmp * eased);
      const ny = node.anchorY * eased + Math.cos(time * 0.52 + node.phase * 1.2) * (DRIFT_Y * motionAmp * eased);
      const nz = node.anchorZ * eased + Math.sin(time * 0.38 + node.phase * 0.9) * (DRIFT_Z * motionAmp * eased);
      node.mesh.position.set(nx, ny, nz);
    }

    camera.lookAt(0, 0, 0);
    renderer.render(scene, camera);
  }

  async function main() {
    const includeMock = shouldShowMocks();
    setupMockToggle(includeMock);
    try {
      await renderNetwork(includeMock);
      resize();
      animate(0);
    } catch {
      renderError("네트워크 데이터를 불러오지 못했습니다.");
    }
  }

  main();
})();
