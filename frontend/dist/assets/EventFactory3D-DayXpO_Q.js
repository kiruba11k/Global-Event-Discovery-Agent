import{r as n,j as e}from"./index-3k0vFXS4.js";import{V as A,c as re,_ as ee,S as se,u as Y,W as K,d as ae,M as ne,e as oe,f as F,g as q,a as z,C as ie}from"./extends-yFqWNnD9.js";function ce(r,a=Math.PI/3){const o=Math.cos(a),s=(1+1e-10)*100,t=[new A,new A,new A],u=new A,f=new A,p=new A,i=new A;function g(l){const m=~~(l.x*s),c=~~(l.y*s),M=~~(l.z*s);return`${m},${c},${M}`}const d=r.index?r.toNonIndexed():r,v=d.attributes.position,h={};for(let l=0,m=v.count/3;l<m;l++){const c=3*l,M=t[0].fromBufferAttribute(v,c+0),y=t[1].fromBufferAttribute(v,c+1),I=t[2].fromBufferAttribute(v,c+2);u.subVectors(I,y),f.subVectors(M,y);const U=new A().crossVectors(u,f).normalize();for(let x=0;x<3;x++){const B=t[x],D=g(B);D in h||(h[D]=[]),h[D].push(U)}}const C=new Float32Array(v.count*3),w=new re(C,3,!1);for(let l=0,m=v.count/3;l<m;l++){const c=3*l,M=t[0].fromBufferAttribute(v,c+0),y=t[1].fromBufferAttribute(v,c+1),I=t[2].fromBufferAttribute(v,c+2);u.subVectors(I,y),f.subVectors(M,y),p.crossVectors(u,f).normalize();for(let U=0;U<3;U++){const x=t[U],B=g(x),D=h[B];i.set(0,0,0);for(let R=0,V=D.length;R<V;R++){const T=D[R];p.dot(T)>o&&i.add(T)}i.normalize(),w.setXYZ(c+U,i.x,i.y,i.z)}}return d.setAttribute("normal",w),d}const ue={uniforms:{tDiffuse:{value:null},h:{value:1/512}},vertexShader:`
      varying vec2 vUv;

      void main() {

        vUv = uv;
        gl_Position = projectionMatrix * modelViewMatrix * vec4( position, 1.0 );

      }
  `,fragmentShader:`
    uniform sampler2D tDiffuse;
    uniform float h;

    varying vec2 vUv;

    void main() {

    	vec4 sum = vec4( 0.0 );

    	sum += texture2D( tDiffuse, vec2( vUv.x - 4.0 * h, vUv.y ) ) * 0.051;
    	sum += texture2D( tDiffuse, vec2( vUv.x - 3.0 * h, vUv.y ) ) * 0.0918;
    	sum += texture2D( tDiffuse, vec2( vUv.x - 2.0 * h, vUv.y ) ) * 0.12245;
    	sum += texture2D( tDiffuse, vec2( vUv.x - 1.0 * h, vUv.y ) ) * 0.1531;
    	sum += texture2D( tDiffuse, vec2( vUv.x, vUv.y ) ) * 0.1633;
    	sum += texture2D( tDiffuse, vec2( vUv.x + 1.0 * h, vUv.y ) ) * 0.1531;
    	sum += texture2D( tDiffuse, vec2( vUv.x + 2.0 * h, vUv.y ) ) * 0.12245;
    	sum += texture2D( tDiffuse, vec2( vUv.x + 3.0 * h, vUv.y ) ) * 0.0918;
    	sum += texture2D( tDiffuse, vec2( vUv.x + 4.0 * h, vUv.y ) ) * 0.051;

    	gl_FragColor = sum;

    }
  `},le={uniforms:{tDiffuse:{value:null},v:{value:1/512}},vertexShader:`
    varying vec2 vUv;

    void main() {

      vUv = uv;
      gl_Position = projectionMatrix * modelViewMatrix * vec4( position, 1.0 );

    }
  `,fragmentShader:`

  uniform sampler2D tDiffuse;
  uniform float v;

  varying vec2 vUv;

  void main() {

    vec4 sum = vec4( 0.0 );

    sum += texture2D( tDiffuse, vec2( vUv.x, vUv.y - 4.0 * v ) ) * 0.051;
    sum += texture2D( tDiffuse, vec2( vUv.x, vUv.y - 3.0 * v ) ) * 0.0918;
    sum += texture2D( tDiffuse, vec2( vUv.x, vUv.y - 2.0 * v ) ) * 0.12245;
    sum += texture2D( tDiffuse, vec2( vUv.x, vUv.y - 1.0 * v ) ) * 0.1531;
    sum += texture2D( tDiffuse, vec2( vUv.x, vUv.y ) ) * 0.1633;
    sum += texture2D( tDiffuse, vec2( vUv.x, vUv.y + 1.0 * v ) ) * 0.1531;
    sum += texture2D( tDiffuse, vec2( vUv.x, vUv.y + 2.0 * v ) ) * 0.12245;
    sum += texture2D( tDiffuse, vec2( vUv.x, vUv.y + 3.0 * v ) ) * 0.0918;
    sum += texture2D( tDiffuse, vec2( vUv.x, vUv.y + 4.0 * v ) ) * 0.051;

    gl_FragColor = sum;

  }
  `},j=1e-5;function ve(r,a,o){const s=new se,t=o-j;return s.absarc(j,j,j,-Math.PI/2,-Math.PI,!0),s.absarc(j,a-t*2,j,Math.PI,Math.PI/2,!0),s.absarc(r-t*2,a-t*2,j,Math.PI/2,0,!0),s.absarc(r-t*2,j,j,0,-Math.PI/2,!0),s}const S=n.forwardRef(function({args:[a=1,o=1,s=1]=[],radius:t=.05,steps:u=1,smoothness:f=4,bevelSegments:p=4,creaseAngle:i=.4,children:g,...d},v){const h=n.useMemo(()=>ve(a,o,t),[a,o,t]),C=n.useMemo(()=>({depth:s-t*2,bevelEnabled:!0,bevelSegments:p*2,steps:u,bevelSize:t-j,bevelThickness:t,curveSegments:f}),[s,t,f]),w=n.useRef(null);return n.useLayoutEffect(()=>{w.current&&(w.current.center(),ce(w.current,i))},[h,C]),n.createElement("mesh",ee({ref:v},d),n.createElement("extrudeGeometry",{ref:w,args:[h,C]}),g)}),fe=n.forwardRef(({scale:r=10,frames:a=1/0,opacity:o=1,width:s=1,height:t=1,blur:u=1,near:f=0,far:p=10,resolution:i=512,smooth:g=!0,color:d="#000000",depthWrite:v=!1,renderOrder:h,...C},w)=>{const l=n.useRef(null),m=Y(b=>b.scene),c=Y(b=>b.gl),M=n.useRef(null);s=s*(Array.isArray(r)?r[0]:r||1),t=t*(Array.isArray(r)?r[1]:r||1);const[y,I,U,x,B,D,R]=n.useMemo(()=>{const b=new K(i,i),W=new K(i,i);W.texture.generateMipmaps=b.texture.generateMipmaps=!1;const X=new ae(s,t).rotateX(Math.PI/2),te=new ne(X),G=new oe;G.depthTest=G.depthWrite=!1,G.onBeforeCompile=E=>{E.uniforms={...E.uniforms,ucolor:{value:new F(d)}},E.fragmentShader=E.fragmentShader.replace("void main() {",`uniform vec3 ucolor;
           void main() {
          `),E.fragmentShader=E.fragmentShader.replace("vec4( vec3( 1.0 - fragCoordZ ), opacity );","vec4( ucolor * fragCoordZ * 2.0, ( 1.0 - fragCoordZ ) * 1.0 );")};const Z=new q(ue),$=new q(le);return $.depthTest=Z.depthTest=!1,[b,X,G,te,Z,$,W]},[i,s,t,r,d]),V=b=>{x.visible=!0,x.material=B,B.uniforms.tDiffuse.value=y.texture,B.uniforms.h.value=b*1/256,c.setRenderTarget(R),c.render(x,M.current),x.material=D,D.uniforms.tDiffuse.value=R.texture,D.uniforms.v.value=b*1/256,c.setRenderTarget(y),c.render(x,M.current),x.visible=!1};let T=0,O,H;return z(()=>{M.current&&(a===1/0||T<a)&&(T++,O=m.background,H=m.overrideMaterial,l.current.visible=!1,m.background=null,m.overrideMaterial=U,c.setRenderTarget(y),c.render(m,M.current),V(u),g&&V(u*.4),c.setRenderTarget(null),l.current.visible=!0,m.overrideMaterial=H,m.background=O)}),n.useImperativeHandle(w,()=>l.current,[]),n.createElement("group",ee({"rotation-x":Math.PI/2},C,{ref:l}),n.createElement("mesh",{renderOrder:h,geometry:I,scale:[1,-1,1],rotation:[-Math.PI/2,0,0]},n.createElement("meshBasicMaterial",{transparent:!0,map:y.texture,opacity:o,depthWrite:v})),n.createElement("orthographicCamera",{ref:M,args:[-s/2,s/2,t/2,-t/2,f,p]}))}),me="#F6EDDD",de="#E4D6BC",_="#22313B",he="#12907C",xe="#F0633F",pe="#F2A71B",L="#FFD98A",k="#D9C49A",P=[-3.4,0,3.4],ge=[he,xe,pe],N=7.2,Me=9,J=3,ye=[new F(k),new F("#20B39A"),new F("#FF7A52"),new F(_)];function Q(r){return r<P[0]?0:r<P[1]?1:r<P[2]?2:3}function De({offset:r}){const a=n.useRef(),o=n.useRef(),s=n.useRef(),t=n.useMemo(()=>new F(k),[]);return z(({clock:u})=>{const f=(u.elapsedTime/Me+r)%1,p=-N+f*N*2,i=a.current;if(!i)return;i.position.x=p;let g=0;for(const v of P){const h=Math.abs(p-v);h<.9&&(g=Math.max(g,Math.cos(h/.9*Math.PI*.5)))}const d=1+g*.12;i.scale.set(d,d,d),i.position.y=.62+g*.1,t.copy(ye[Q(p)]),o.current&&o.current.color.lerp(t,.15),s.current&&(s.current.visible=Q(p)===3)}),e.jsxs("group",{ref:a,position:[-N,.62,0],castShadow:!0,children:[e.jsx(S,{args:[.95,.95,.95],radius:.09,smoothness:4,castShadow:!0,children:e.jsx("meshStandardMaterial",{ref:o,color:k,roughness:.55,metalness:.05})}),e.jsxs("mesh",{position:[0,.482,0],rotation:[-Math.PI/2,0,0],children:[e.jsx("planeGeometry",{args:[.22,.96]}),e.jsx("meshStandardMaterial",{color:"#FFFDF6",roughness:.4,transparent:!0,opacity:.85})]}),e.jsx("group",{ref:s,visible:!1,children:e.jsx(S,{args:[.99,.18,.99],radius:.04,position:[0,.12,0],children:e.jsx("meshStandardMaterial",{color:L,roughness:.3,metalness:.35})})})]})}function je({x:r,color:a,phase:o}){const s=n.useRef(),t=n.useRef();return z(({clock:u})=>{const f=u.elapsedTime;s.current&&(s.current.material.emissiveIntensity=1.6+Math.sin(f*4+o)*1.2),t.current&&(t.current.position.y=1.02+Math.sin(f*2.4+o)*.22)}),e.jsxs("group",{position:[r,0,0],children:[e.jsx(S,{args:[2.3,1.55,2.5],radius:.16,position:[0,2.05,0],castShadow:!0,children:e.jsx("meshStandardMaterial",{color:a,roughness:.38,metalness:.05})}),[-1,1].map(u=>e.jsx(S,{args:[.42,1.7,2.3],radius:.1,position:[u*.95,.55,0],castShadow:!0,children:e.jsx("meshStandardMaterial",{color:a,roughness:.45,metalness:.05})},u)),e.jsx(S,{args:[1.5,.8,.08],radius:.06,position:[0,2.05,1.28],children:e.jsx("meshStandardMaterial",{color:"#FBF6EA",roughness:.25})}),e.jsxs("mesh",{ref:t,position:[0,1.02,0],children:[e.jsx("boxGeometry",{args:[1.7,.06,1.9]}),e.jsx("meshStandardMaterial",{color:a,emissive:a,emissiveIntensity:.7,transparent:!0,opacity:.4})]}),e.jsxs("mesh",{position:[.6,2.98,0],castShadow:!0,children:[e.jsx("cylinderGeometry",{args:[.16,.2,.4,16]}),e.jsx("meshStandardMaterial",{color:_,roughness:.5})]}),e.jsxs("mesh",{ref:s,position:[-.75,2.62,1.28],children:[e.jsx("sphereGeometry",{args:[.08,16,16]}),e.jsx("meshStandardMaterial",{color:L,emissive:L,emissiveIntensity:2})]})]})}function Se(){const r=n.useRef();return z(({clock:a})=>{r.current&&(r.current.rotation.y=Math.sin(a.elapsedTime*.18)*.05-.12)}),e.jsxs("group",{ref:r,rotation:[0,-.12,0],children:[e.jsx(S,{args:[15.4,.55,2],radius:.18,position:[0,0,0],receiveShadow:!0,castShadow:!0,children:e.jsx("meshStandardMaterial",{color:me,roughness:.6})}),e.jsx(S,{args:[15.8,.28,2.4],radius:.14,position:[0,-.38,0],receiveShadow:!0,children:e.jsx("meshStandardMaterial",{color:de,roughness:.65})}),e.jsx("group",{position:[-7.3,1.1,0],children:e.jsxs("mesh",{castShadow:!0,children:[e.jsx("cylinderGeometry",{args:[.85,.5,1.15,4]}),e.jsx("meshStandardMaterial",{color:_,roughness:.5})]})}),e.jsxs("group",{position:[7.35,.5,0],children:[e.jsx(S,{args:[1.5,.45,1.5],radius:.08,castShadow:!0,receiveShadow:!0,children:e.jsx("meshStandardMaterial",{color:"#C98B3D",roughness:.55})}),e.jsx(S,{args:[.95,.5,.95],radius:.08,position:[0,.48,0],castShadow:!0,children:e.jsx("meshStandardMaterial",{color:_,roughness:.45})}),e.jsx(S,{args:[.99,.14,.99],radius:.04,position:[0,.44,0],children:e.jsx("meshStandardMaterial",{color:L,roughness:.3,metalness:.35})})]}),P.map((a,o)=>e.jsx(je,{x:a,color:ge[o],phase:o*2.1},o)),Array.from({length:J},(a,o)=>e.jsx(De,{offset:o/J},o)),e.jsx(fe,{position:[0,-.55,0],opacity:.42,scale:22,blur:2.6,far:4.5,resolution:512,color:"#22313B"})]})}function Ue(){return e.jsx("div",{className:"ef3d-canvas","aria-hidden":"true",children:e.jsxs(ie,{shadows:!0,dpr:[1,2],camera:{position:[.4,4.4,10.2],fov:34},gl:{antialias:!0,alpha:!0},style:{background:"transparent"},children:[e.jsx("ambientLight",{intensity:.85}),e.jsx("directionalLight",{position:[6,9,6],intensity:1.5,castShadow:!0,"shadow-mapSize":[1024,1024],"shadow-camera-left":-10,"shadow-camera-right":10,"shadow-camera-top":10,"shadow-camera-bottom":-10}),e.jsx("directionalLight",{position:[-7,5,-4],intensity:.45,color:"#FFE9C9"}),e.jsx("group",{position:[0,-1.1,0],children:e.jsx(Se,{})})]})})}export{Ue as default};
