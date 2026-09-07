import React, { useEffect, useRef } from "react";
import type { LiveSnapshot, SnapshotVehicle } from "../types/simulation";

interface RoundaboutMapProps {
  snapshot: LiveSnapshot | null;
  width?: number;
  height?: number;
  laneWidth?: number;
  lanes?: number;
  showCrosswalks?: boolean;
  debug?: boolean;
}

export const RoundaboutMap: React.FC<RoundaboutMapProps> = ({
  snapshot,
  width = 800,
  height = 680,
  laneWidth = 3.5,
  lanes = 2,
  showCrosswalks = true,
  debug = false,
}) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animFrameIdRef = useRef<number | null>(null);

  const snapshotRef = useRef<LiveSnapshot | null>(null);
  const prevSnapshotRef = useRef<LiveSnapshot | null>(null);
  const lastSnapshotTimeRef = useRef<number>(0);

  useEffect(() => {
    prevSnapshotRef.current = snapshotRef.current;
    snapshotRef.current = snapshot;
    lastSnapshotTimeRef.current = performance.now();
  }, [snapshot]);

  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;

    let active = true;

    const render = () => {
      if (!active) return;

      const current = snapshotRef.current;
      const previous = prevSnapshotRef.current;
      const lastTime = lastSnapshotTimeRef.current;

      if (!current) {
        // Draw grass background while waiting for data
        ctx.fillStyle = "#557d35";
        ctx.fillRect(0, 0, width, height);
        animFrameIdRef.current = requestAnimationFrame(render);
        return;
      }

      const controller = current.controller;
      const innerRadius =
        controller.type === "roundabout" ? controller.innerRadius : 10;
      const outerRadius =
        controller.type === "roundabout" ? controller.outerRadius : 20;
      const initialArmReach = outerRadius + 42;
      const scale = Math.min(width, height) / (initialArmReach * 2);
      const armReach = Math.max(width, height) / scale + 10;
      const toCanvas = (x: number, y: number): [number, number] => [
        width / 2 + x * scale,
        height / 2 - y * scale,
      ];

      // Interpolate factor t
      const elapsed = performance.now() - lastTime;
      const stepDuration = current.deltaTime ? current.deltaTime * 1000 : 100;
      const t = Math.max(0, Math.min(1, elapsed / stepDuration));

      ctx.fillStyle = "#557d35";
      ctx.fillRect(0, 0, width, height);
      ctx.strokeStyle = "rgba(28,58,28,.2)";
      ctx.lineWidth = 1;
      for (let y = 0; y < height; y += 18) {
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(width, y);
        ctx.stroke();
      }

      const armWidth = laneWidth * (lanes * 2);
      ctx.fillStyle = "#343b42";
      fillWorldRect(
        ctx,
        toCanvas,
        -armWidth / 2,
        outerRadius,
        armWidth,
        armReach - outerRadius,
      );
      fillWorldRect(
        ctx,
        toCanvas,
        -armWidth / 2,
        -armReach,
        armWidth,
        armReach - outerRadius,
      );
      fillWorldRect(
        ctx,
        toCanvas,
        outerRadius,
        -armWidth / 2,
        armReach - outerRadius,
        armWidth,
      );
      fillWorldRect(
        ctx,
        toCanvas,
        -armReach,
        -armWidth / 2,
        armReach - outerRadius,
        armWidth,
      );

      const [cx, cy] = toCanvas(0, 0);
      ctx.fillStyle = "#343b42";
      ctx.beginPath();
      ctx.arc(cx, cy, outerRadius * scale, 0, Math.PI * 2);
      ctx.fill();
      ctx.strokeStyle = "#e5eaed";
      ctx.lineWidth = 2;
      ctx.setLineDash([]);
      ctx.stroke();

      ctx.beginPath();
      ctx.arc(
        cx,
        cy,
        ((innerRadius + outerRadius) / 2) * scale,
        0,
        Math.PI * 2,
      );
      ctx.strokeStyle = "rgba(229, 234, 237, 0.65)";
      ctx.lineWidth = 1.5;
      ctx.setLineDash([6, 8]);
      ctx.stroke();
      ctx.setLineDash([]);

      ctx.fillStyle = "#557d35";
      ctx.beginPath();
      ctx.arc(cx, cy, innerRadius * scale, 0, Math.PI * 2);
      ctx.fill();
      ctx.strokeStyle = "#e5eaed";
      ctx.lineWidth = 2;
      ctx.stroke();

      drawApproachMarkings(
        ctx,
        toCanvas,
        outerRadius,
        armReach,
        armWidth,
        showCrosswalks,
      );
      drawEntryYieldSigns(ctx, toCanvas, outerRadius, armReach, armWidth);

      // Interpolate vehicle positions
      const prevVehiclesMap = new Map<string, SnapshotVehicle>();
      if (previous) {
        for (const pv of previous.vehicles) {
          prevVehiclesMap.set(pv.id, pv);
        }
      }

      for (const vehicle of current.vehicles) {
        if (vehicle.state === "exited") continue;

        let renderX = vehicle.x;
        let renderY = vehicle.y;
        let renderHeading = vehicle.heading;

        const prevVehicle = prevVehiclesMap.get(vehicle.id);
        if (prevVehicle) {
          renderX = prevVehicle.x + t * (vehicle.x - prevVehicle.x);
          renderY = prevVehicle.y + t * (vehicle.y - prevVehicle.y);

          // Interpolate heading along shortest angular path
          let diff = vehicle.heading - prevVehicle.heading;
          while (diff < -180) diff += 360;
          while (diff > 180) diff -= 360;
          renderHeading = (prevVehicle.heading + t * diff + 360) % 360;
        }

        drawRoundaboutVehicle(
          ctx,
          { ...vehicle, x: renderX, y: renderY, heading: renderHeading },
          toCanvas,
          scale,
        );
      }

      if (debug) drawDebugLabel(ctx, current, width);

      animFrameIdRef.current = requestAnimationFrame(render);
    };

    render();

    return () => {
      active = false;
      if (animFrameIdRef.current) {
        cancelAnimationFrame(animFrameIdRef.current);
      }
    };
  }, [width, height, laneWidth, showCrosswalks, debug]);

  return (
    <canvas
      ref={canvasRef}
      width={width}
      height={height}
      style={{ display: "block", borderRadius: "8px" }}
    />
  );
};

function fillWorldRect(
  ctx: CanvasRenderingContext2D,
  toCanvas: (x: number, y: number) => [number, number],
  x: number,
  y: number,
  width: number,
  height: number,
) {
  const [left, top] = toCanvas(x, y + height);
  const [right, bottom] = toCanvas(x + width, y);
  ctx.fillRect(left, top, right - left, bottom - top);
}

function drawApproachMarkings(
  ctx: CanvasRenderingContext2D,
  toCanvas: (x: number, y: number) => [number, number],
  radius: number,
  armReach: number,
  armWidth: number,
  showCrosswalks: boolean,
) {
  ctx.strokeStyle = "#d7dde0";
  ctx.lineWidth = 1.5;
  ctx.setLineDash([]);
  const edge = armWidth / 2;
  for (const x of [-edge, edge]) {
    drawWorldLine(ctx, toCanvas, x, radius, x, armReach);
    drawWorldLine(ctx, toCanvas, x, -radius, x, -armReach);
  }
  for (const y of [-edge, edge]) {
    drawWorldLine(ctx, toCanvas, radius, y, armReach, y);
    drawWorldLine(ctx, toCanvas, -radius, y, -armReach, y);
  }
  ctx.lineWidth = 1.4;
  for (const offset of [
    -laneWidthForArm(armWidth),
    0,
    laneWidthForArm(armWidth),
  ]) {
    ctx.strokeStyle = offset === 0 ? "#e7bd2e" : "rgba(255,255,255,.7)";
    ctx.setLineDash(offset === 0 ? [] : [8, 10]);
    drawWorldLine(ctx, toCanvas, offset, radius, offset, armReach);
    drawWorldLine(ctx, toCanvas, offset, -radius, offset, -armReach);
    drawWorldLine(ctx, toCanvas, radius, offset, armReach, offset);
    drawWorldLine(ctx, toCanvas, -radius, offset, -armReach, offset);
  }
  ctx.setLineDash([]);
  if (!showCrosswalks) return;
  ctx.fillStyle = "rgba(255,255,255,.78)";
  for (let i = -5; i <= 5; i += 1) {
    const offset = i * (armWidth / 12);
    const [x1, y1] = toCanvas(offset, radius + 1.5);
    ctx.fillRect(x1 - 3, y1 - 5, 6, 10);
    const [x2, y2] = toCanvas(offset, -radius - 1.5);
    ctx.fillRect(x2 - 3, y2 - 5, 6, 10);
    const [x3, y3] = toCanvas(radius + 1.5, offset);
    ctx.fillRect(x3 - 5, y3 - 3, 10, 6);
    const [x4, y4] = toCanvas(-radius - 1.5, offset);
    ctx.fillRect(x4 - 5, y4 - 3, 10, 6);
  }
}

function laneWidthForArm(armWidth: number): number {
  return armWidth / 4;
}

function drawEntryYieldSigns(
  ctx: CanvasRenderingContext2D,
  toCanvas: (x: number, y: number) => [number, number],
  radius: number,
  armReach: number,
  armWidth: number,
) {
  const edge = armWidth / 2;
  const entries: Array<[number, number, "north" | "south" | "east" | "west"]> =
    [
      [0, radius + 3, "north"],
      [0, -radius - 3, "south"],
      [radius + 3, 0, "east"],
      [-radius - 3, 0, "west"],
    ];
  for (const [x, y, direction] of entries) {
    const [cx, cy] = toCanvas(x, y);
    ctx.fillStyle = "#f5f6f3";
    ctx.strokeStyle = "#d33b35";
    ctx.lineWidth = 2;
    ctx.beginPath();
    if (direction === "north" || direction === "south") {
      ctx.moveTo(cx, direction === "north" ? cy + 10 : cy - 10);
      ctx.lineTo(cx - 9, direction === "north" ? cy - 7 : cy + 7);
      ctx.lineTo(cx + 9, direction === "north" ? cy - 7 : cy + 7);
    } else {
      ctx.moveTo(direction === "east" ? cx - 10 : cx + 10, cy);
      ctx.lineTo(direction === "east" ? cx + 7 : cx - 7, cy - 9);
      ctx.lineTo(direction === "east" ? cx + 7 : cx - 7, cy + 9);
    }
    ctx.closePath();
    ctx.fill();
    ctx.stroke();
  }
  ctx.strokeStyle = "rgba(255,255,255,.55)";
  ctx.lineWidth = 1;
  ctx.setLineDash([5, 7]);
  drawWorldLine(ctx, toCanvas, -edge, armReach, edge, armReach);
  drawWorldLine(ctx, toCanvas, -edge, -armReach, edge, -armReach);
  drawWorldLine(ctx, toCanvas, armReach, -edge, armReach, edge);
  drawWorldLine(ctx, toCanvas, -armReach, -edge, -armReach, edge);
  ctx.setLineDash([]);
}

function drawWorldLine(
  ctx: CanvasRenderingContext2D,
  toCanvas: (x: number, y: number) => [number, number],
  x1: number,
  y1: number,
  x2: number,
  y2: number,
) {
  const [a, b] = toCanvas(x1, y1);
  const [c, d] = toCanvas(x2, y2);
  ctx.beginPath();
  ctx.moveTo(a, b);
  ctx.lineTo(c, d);
  ctx.stroke();
}

function carColor(id: string): string {
  const palette = [
    "#4d96ff",
    "#f8961e",
    "#43aa8b",
    "#e76f51",
    "#c77dff",
    "#f9c74f",
  ];
  let hash = 0;
  for (const character of id)
    hash = (hash * 31 + character.charCodeAt(0)) >>> 0;
  return palette[hash % palette.length];
}

function drawRoundaboutVehicle(
  ctx: CanvasRenderingContext2D,
  vehicle: SnapshotVehicle,
  toCanvas: (x: number, y: number) => [number, number],
  scale: number,
) {
  const [cx, cy] = toCanvas(vehicle.x, vehicle.y);
  const length = Math.max(4.5, vehicle.length) * scale;
  const width = Math.max(2, vehicle.width) * scale;
  ctx.save();
  ctx.translate(cx, cy);
  ctx.rotate((vehicle.heading * Math.PI) / 180);

  ctx.fillStyle = carColor(vehicle.id);
  ctx.strokeStyle = "#172027";
  ctx.lineWidth = 2;

  ctx.beginPath();
  ctx.roundRect(-width / 2, -length / 2, width, length, 4);
  ctx.fill();
  ctx.stroke();

  ctx.fillStyle = "rgba(224,243,255,.8)";
  ctx.beginPath();
  ctx.roundRect(-width * 0.34, -length * 0.28, width * 0.68, length * 0.24, 2);
  ctx.fill();

  // Draw brake lights if waiting
  if (vehicle.state === "waiting") {
    ctx.fillStyle = "#ff1744";
    ctx.beginPath();
    ctx.arc(-width * 0.3, length / 2, 2.5, 0, Math.PI * 2);
    ctx.arc(width * 0.3, length / 2, 2.5, 0, Math.PI * 2);
    ctx.fill();
  }

  ctx.restore();
}

function drawDebugLabel(
  ctx: CanvasRenderingContext2D,
  snapshot: LiveSnapshot | null,
  width: number,
) {
  ctx.fillStyle = "rgba(15,20,24,.86)";
  ctx.fillRect(width - 200, 14, 186, 38);
  ctx.fillStyle = "#fff";
  ctx.font = "11px monospace";
  ctx.fillText(
    `ROUNDABOUT  T ${(snapshot?.timestamp ?? 0).toFixed(1)}s`,
    width - 188,
    38,
  );
}
