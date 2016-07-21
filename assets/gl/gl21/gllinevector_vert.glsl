/*
 * OpenGL vertex shader used for rendering GLVector instances in
 * line mode.
 *
 * Author: Paul McCarthy <pauldmccarthy@gmail.com>
 */
#version 120

/*
 * Vector image containing XYZ vector data.
 */
uniform sampler3D vectorTexture;

/*
 * Transformations between voxel and 
 * display coordinate systems.
 */
uniform mat4 displayToVoxMat;
uniform mat4 voxToDisplayMat;

/*
 * Transformation matrix which transforms the
 * vector texture data to its original data range.
 */
uniform mat4 voxValXform;

/*
 * Constant offset to add to voxel coordinates.
 */
uniform vec3 voxelOffset;

/*
 * Shape of the image texture.
 */
uniform vec3 imageShape;

/*
 * Dimensions of one voxel in the image texture.
 */
uniform vec3 imageDims;

/*
 * If true, the vectors are 
 * inverted about the x axis.
 */
uniform bool xFlip;

/*
 * Line vectors are interpreted as directed - each
 * line begins in the centre of its voxel, and extends
 * outwards.
 */
uniform bool directed;

/*
 * If true, each vector is scaled to have a length 
 * of 1 in the image coordinate system.
 */
uniform bool scaleLength;

/*
 * The current vertex on the current line.
 */
attribute vec3 vertex;

/*
 * Vertex index - the built-in gl_VertexID
 * variable is not available in GLSL 120
 */
attribute float vertexID;


varying vec3 fragVoxCoord;
varying vec3 fragTexCoord;
varying vec4 fragColourFactor;

void main(void) {

  
  vec3  texCoord;
  vec3  vector;
  vec3  voxCoord;
  float vectorLen;

  /*
   * The voxCoord vector contains the exact integer
   * voxel coordinates - we cannot interpolate vector
   * directions.
   *
   * There is no round function in GLSL 1.2, so we use
   * floor(x + 0.5).
   */
  voxCoord = (displayToVoxMat * vec4(vertex, 1)).xyz;
  voxCoord = floor(vertVoxCoord + voxelOffset);
  
  /*
   * Normalise the voxel coordinates to [0.0, 1.0],
   * so they can be used for texture lookup. Add
   * 0.5 to the voxel coordinates first, to re-centre
   * voxel coordinates from  from [i - 0.5, i + 0.5]
   * to [i, i + 1].
   */
  texCoord = (voxCoord + 0.5) / imageShape;

  /*
   * Retrieve the vector values for this voxel
   */
  vector = texture3D(vectorTexture, texCoord).xyz;

  /*
   * Transform the vector values  from their
   * texture range of [0,1] to the original
   * data range
   */
  vector   *= voxValXform[0].x;
  vector   += voxValXform[3].x;
  vectorLen = length(vector);

  /* Invert about the x axis if necessary */
  if (xFlip)
    vector.x = -vector.x;

  /* 
   * Kill the vector if its length is 0. 
   * We have to be tolerant of errors, 
   * because of the transformation to/
   * from the texture data range. This 
   * may end up being too tolerant.
   */
  if (vectorLen < 0.0001) {
    fragColourFactor = vec4(0, 0, 0, 0);
    return;
  }


  if (scaleLength) {

    /*
     * Scale the vector so it has length 0.5. 
     */
    vector /= 2 * vectorLen;

    /*
     * Scale the vector by the minimum voxel length,
     * so it is a unit vector within real world space 
     */
    vector /= imageDims / min(imageDims.x, min(imageDims.y, imageDims.z));
  }

  /*
   * Vertices are coming in as line pairs - flip
   * every second vertex about the origin
   */
  if (mod(vertexID, 2) == 1) {
    if (directed) vector = vec3(0, 0, 0);
    else          vector = -vector;
  }

  /*
   * Output the final vertex position - offset
   * the voxel coordinates by the vector values,
   * and transform back to display coordinates
   */
  gl_Position = gl_ModelViewProjectionMatrix *
                voxToDisplayMat              *
                vec4(voxCoord + vector, 1);

  fragVoxCoord     = voxCoord;
  fragTexCoord     = texCoord;
  fragColourFactor = vec4(1, 1, 1, 1);
}
