import { LogLevel } from "@framework/live2dcubismframework";

export const CanvasSize: { width: number; height: number } | "auto" = "auto";
export const ShaderPath = "./live2d/Framework/Shaders/WebGL/";

export const MotionGroupIdle = "Idle";
export const MotionGroupTapBody = "TapBody";
export const HitAreaNameHead = "Head";
export const HitAreaNameBody = "Body";

export const PriorityNone = 0;
export const PriorityIdle = 1;
export const PriorityNormal = 2;
export const PriorityForce = 3;

export const MOCConsistencyValidationEnable = false;
export const MotionConsistencyValidationEnable = false;
export const DebugLogEnable = false;
export const DebugTouchLogEnable = false;
export const CubismLoggingLevel: LogLevel = LogLevel.LogLevel_Warning;
