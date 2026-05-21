import type { SpeechLipSyncEnvelope } from "./types";

export function downsampleFloat32(input: Float32Array, inputSampleRate: number, outputSampleRate: number): number[] {
  if (!input.length) {
    return [];
  }
  if (!Number.isFinite(inputSampleRate) || inputSampleRate <= 0 || inputSampleRate === outputSampleRate) {
    return Array.from(input);
  }

  const ratio = inputSampleRate / outputSampleRate;
  const outputLength = Math.max(1, Math.floor(input.length / ratio));
  const output: number[] = [];
  for (let i = 0; i < outputLength; i += 1) {
    const start = Math.floor(i * ratio);
    const end = Math.min(input.length, Math.floor((i + 1) * ratio));
    let total = 0;
    let count = 0;
    for (let j = start; j < end; j += 1) {
      total += input[j] || 0;
      count += 1;
    }
    output.push(count ? total / count : input[start] || 0);
  }
  return output;
}

function readAscii(view: DataView, offset: number, length: number): string {
  let result = "";
  for (let i = 0; i < length; i += 1) {
    result += String.fromCharCode(view.getUint8(offset + i));
  }
  return result;
}

function readWavSample(
  view: DataView,
  offset: number,
  bitsPerSample: number,
  audioFormat: number
): number {
  if (audioFormat === 3 && bitsPerSample === 32) {
    return view.getFloat32(offset, true);
  }

  if (audioFormat !== 1) {
    return 0;
  }

  if (bitsPerSample === 8) {
    return (view.getUint8(offset) - 128) / 128;
  }
  if (bitsPerSample === 16) {
    return view.getInt16(offset, true) / 32768;
  }
  if (bitsPerSample === 24) {
    let value =
      view.getUint8(offset) |
      (view.getUint8(offset + 1) << 8) |
      (view.getUint8(offset + 2) << 16);
    if (value & 0x800000) {
      value |= 0xff000000;
    }
    return value / 8388608;
  }
  if (bitsPerSample === 32) {
    return view.getInt32(offset, true) / 2147483648;
  }

  return 0;
}

export function buildSpeechLipSyncEnvelope(audioBase64: string): SpeechLipSyncEnvelope | null {
  try {
    const binary = window.atob(audioBase64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i += 1) {
      bytes[i] = binary.charCodeAt(i);
    }

    const view = new DataView(bytes.buffer);
    if (
      view.byteLength < 44 ||
      readAscii(view, 0, 4) !== "RIFF" ||
      readAscii(view, 8, 4) !== "WAVE"
    ) {
      return null;
    }

    let audioFormat = 0;
    let channels = 0;
    let sampleRate = 0;
    let bitsPerSample = 0;
    let blockAlign = 0;
    let dataOffset = 0;
    let dataSize = 0;

    for (let offset = 12; offset + 8 <= view.byteLength;) {
      const chunkId = readAscii(view, offset, 4);
      const chunkSize = view.getUint32(offset + 4, true);
      const chunkDataOffset = offset + 8;

      if (chunkDataOffset + chunkSize > view.byteLength) {
        break;
      }

      if (chunkId === "fmt " && chunkSize >= 16) {
        audioFormat = view.getUint16(chunkDataOffset, true);
        channels = view.getUint16(chunkDataOffset + 2, true);
        sampleRate = view.getUint32(chunkDataOffset + 4, true);
        blockAlign = view.getUint16(chunkDataOffset + 12, true);
        bitsPerSample = view.getUint16(chunkDataOffset + 14, true);
      } else if (chunkId === "data") {
        dataOffset = chunkDataOffset;
        dataSize = chunkSize;
      }

      offset = chunkDataOffset + chunkSize + (chunkSize % 2);
    }

    if (
      !dataOffset ||
      !dataSize ||
      !sampleRate ||
      !channels ||
      !blockAlign ||
      !bitsPerSample ||
      (audioFormat !== 1 && audioFormat !== 3)
    ) {
      return null;
    }

    const frameCount = Math.floor(dataSize / blockAlign);
    if (frameCount <= 0) {
      return null;
    }

    const mono = new Float32Array(frameCount);
    const bytesPerSample = Math.floor(bitsPerSample / 8);
    for (let frame = 0; frame < frameCount; frame += 1) {
      const frameOffset = dataOffset + frame * blockAlign;
      let mixed = 0;
      for (let channel = 0; channel < channels; channel += 1) {
        mixed += readWavSample(
          view,
          frameOffset + channel * bytesPerSample,
          bitsPerSample,
          audioFormat
        );
      }
      mono[frame] = mixed / channels;
    }

    const duration = frameCount / sampleRate;
    const frameRate = 60;
    const envelopeLength = Math.max(1, Math.ceil(duration * frameRate));
    const rmsValues: number[] = [];
    const windowSamples = Math.max(1, Math.floor(sampleRate * 0.032));

    for (let i = 0; i < envelopeLength; i += 1) {
      const center = Math.floor((i / frameRate) * sampleRate);
      const start = Math.max(0, center - Math.floor(windowSamples / 2));
      const end = Math.min(frameCount, start + windowSamples);
      let sumSquares = 0;
      let count = 0;
      for (let sampleIndex = start; sampleIndex < end; sampleIndex += 1) {
        const sample = mono[sampleIndex] || 0;
        sumSquares += sample * sample;
        count += 1;
      }
      rmsValues.push(count ? Math.sqrt(sumSquares / count) : 0);
    }

    const sorted = [...rmsValues].sort((a, b) => a - b);
    const noiseFloor = sorted[Math.floor(sorted.length * 0.18)] || 0;
    const peak = sorted[sorted.length - 1] || 0;
    const gate = Math.max(0.006, noiseFloor * 2.8, peak * 0.06);
    const range = Math.max(0.001, peak - gate);
    const values: number[] = [];
    let smoothed = 0;

    for (const rms of rmsValues) {
      const gated = rms <= gate ? 0 : Math.min(1, (rms - gate) / range);
      const target = gated <= 0.025 ? 0 : Math.pow(gated, 0.62);
      const follow = target > smoothed ? 0.78 : 0.34;
      smoothed += (target - smoothed) * follow;
      values.push(smoothed < 0.035 ? 0 : Math.min(1, smoothed));
    }

    return { values, frameRate, duration };
  } catch (error) {
    console.warn("[pet-renderer] WAV lip sync envelope parse failed", error);
    return null;
  }
}
