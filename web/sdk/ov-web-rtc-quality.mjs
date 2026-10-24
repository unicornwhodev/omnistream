/**
 * ov-web-rtc 6.6.0's Direct wrapper drops two supported downstream parameters.
 * Forward them at build time, without reaching into a live SDK instance.
 * The underlying stream client consumes maxBitrateKbps (kb/s) and
 * dynamicStreamingMode (0 disables dynamic resolution reduction).
 * Fail closed if the version-pinned wrapper changes; never silently lose them.
 */
export function forwardDirectStreamQuality(code) {
  const create = 'async create(){if(this._props.disableWorkerWs)';
  const createQuality = 'async create(){if(Number.isSafeInteger(this._props.maxBitrateKbps)&&this._props.maxBitrateKbps>=4000&&this._props.maxBitrateKbps<=100000)R.configureOverrideSettings({overrideData:"bitrate="+this._props.maxBitrateKbps});if(this._props.disableWorkerWs)';
  const source = 'fps:this._props.fps},s=this._props.authenticate';
  const replacement = 'fps:this._props.fps,maxBitrateKbps:this._props.maxBitrateKbps,dynamicStreamingMode:this._props.dynamicStreamingMode},s=this._props.authenticate';
  if (code.split(source).length !== 2 || code.split(create).length !== 2 ||
      !code.includes('f[e].maxBitrateKbps') ||
      !code.includes('void 0:N.dynamicStreamingMode')) {
    throw new Error('ov-web-rtc 6.6.0 Direct quality adapter no longer matches the pinned SDK.');
  }
  return code.replace(source, replacement).replace(create, createQuality);
}
