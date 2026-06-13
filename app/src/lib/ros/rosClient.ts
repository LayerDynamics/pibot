/**
 * roslib wrapper for Mission Control's ROS panel. Connects the webview to the robot's
 * rosbridge WebSocket (port 9090, reachable over Nebula) and bridges the ROS 2 topics that
 * `pibot.ros2.bridge` publishes: subscribes `/pibot/estop`, `/pibot/telemetry`,
 * `/pibot/image/compressed`, and publishes `/cmd_vel` (drive). This is the only place the
 * frontend talks ROS — everything else goes through the sidecar.
 */
import { Ros, Topic } from "roslib";

import type { Snapshot } from "../api/types";

export type RosStatus = "idle" | "connecting" | "connected" | "error" | "closed";

export interface RosHandlers {
  onStatus: (status: RosStatus) => void;
  onEstop?: (latched: boolean) => void;
  onTelemetry?: (snap: Snapshot) => void;
  onImageJpegBase64?: (base64: string) => void;
}

interface BoolMsg {
  data: boolean;
}
interface StringMsg {
  data: string;
}
interface TwistMsg {
  linear: { x: number; y: number; z: number };
  angular: { x: number; y: number; z: number };
}

/** Default rosbridge URL for a robot at `address` (the inventory/overlay IP). */
export function rosbridgeUrl(address: string): string {
  return `ws://${address}:9090`;
}

export class RosLink {
  private ros: Ros | null = null;
  private cmdVel: Topic<TwistMsg> | null = null;

  connect(url: string, handlers: RosHandlers): void {
    this.close();
    handlers.onStatus("connecting");
    const ros = new Ros({ url });
    this.ros = ros;

    ros.on("connection", () => handlers.onStatus("connected"));
    ros.on("error", () => handlers.onStatus("error"));
    ros.on("close", () => handlers.onStatus("closed"));

    new Topic<BoolMsg>({ ros, name: "/pibot/estop", messageType: "std_msgs/Bool" }).subscribe(
      (message) => handlers.onEstop?.(Boolean(message.data)),
    );
    new Topic<StringMsg>({ ros, name: "/pibot/telemetry", messageType: "std_msgs/String" }).subscribe(
      (message) => {
        try {
          handlers.onTelemetry?.(JSON.parse(message.data) as Snapshot);
        } catch {
          // A malformed frame must never tear down the stream.
        }
      },
    );
    new Topic<StringMsg>({
      ros,
      name: "/pibot/image/compressed",
      messageType: "sensor_msgs/CompressedImage",
    }).subscribe((message) => handlers.onImageJpegBase64?.(message.data));

    this.cmdVel = new Topic<TwistMsg>({ ros, name: "/cmd_vel", messageType: "geometry_msgs/Twist" });
  }

  /** Publish a Twist on /cmd_vel (linear.x = forward m/s, angular.z = yaw rad/s). */
  drive(linear: number, angular: number): void {
    this.cmdVel?.publish({
      linear: { x: linear, y: 0, z: 0 },
      angular: { x: 0, y: 0, z: angular },
    });
  }

  close(): void {
    if (this.ros) {
      this.ros.close();
      this.ros = null;
    }
    this.cmdVel = null;
  }

  get connected(): boolean {
    return this.ros !== null;
  }
}
