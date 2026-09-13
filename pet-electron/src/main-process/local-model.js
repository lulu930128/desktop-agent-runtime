const fs = require('fs');
const path = require('path');

function resolveAsset(root, relative) {
  if (!relative || /[\\\x00?#]/.test(relative) || relative.split('/').includes('..')) throw new Error('Invalid model asset');
  const base = fs.realpathSync(root);
  const target = fs.realpathSync(path.resolve(base, relative));
  const inside = path.relative(base, target);
  if (inside.startsWith('..') || path.isAbsolute(inside) || !/\.(json|moc3|png|jpg|jpeg|webp)$/i.test(target)) throw new Error('Model asset outside allowed root');
  return target;
}

function normalizePresentation(openLlmDir, descriptor) {
  if (!descriptor || typeof descriptor.modelPath !== 'string') return null;
  const catalog = JSON.parse(fs.readFileSync(path.join(openLlmDir, 'model_dict.json'), 'utf8').replace(/^\uFEFF/, ''));
  if (!catalog.some(item => item.url === `/live2d-models/${descriptor.modelPath}`)) throw new Error('Model is not registered');
  resolveAsset(path.join(openLlmDir, 'live2d-models'), descriptor.modelPath);
  const scale = Number(descriptor.scaleWidth);
  if (!Number.isFinite(scale) || scale < 0.8 || scale > 4) throw new Error('Invalid model scale');
  return { confUid: String(descriptor.confUid || ''), confName: String(descriptor.confName || ''),
    modelUrl: `kuro-model://local/${descriptor.modelPath.split('/').map(encodeURIComponent).join('/')}`, scaleWidth: scale };
}

function registerModelProtocol(protocol, net, openLlmDir) {
  const { pathToFileURL } = require('url');
  protocol.handle('kuro-model', async request => {
    try {
      const url = new URL(request.url);
      if (url.hostname !== 'local' || request.method !== 'GET') return new Response(null, { status: 403 });
      const asset = resolveAsset(path.join(openLlmDir, 'live2d-models'), decodeURIComponent(url.pathname).replace(/^\//, ''));
      return net.fetch(pathToFileURL(asset).href);
    } catch {
      return new Response(null, { status: 404 });
    }
  });
}
module.exports = { resolveAsset, normalizePresentation, registerModelProtocol };
