/*
  ==============================================================================

    WChartTransform.h
    Created: 8 Nov 2025 8:48:40pm
    Author:  Jonathan

  ==============================================================================
*/

#pragma once
#include "JuceHeader.h"

/*
	un viewport rect et son pivot en pixel
	un viewport rect et son pivot mais dans l'unité de référence
	un content rect (contenu total) en unité de référence
	une option pour gérer la conversion x ou y de façon linéaire ou logarithmique
	une option pour inverser l'axe x ou y
	un zoom scale en x ou y
	des presets de zoom scales (utile pour changer les timeframes)
	une option pour snap sur les zoom scales quand on zoom

	une fonction pour zoom sur le max scale (et voir tout le contenu)
	(échantillonnage à seulement ce qui est visible au pixel level)

*/

/*
	enum class SamplingMode
	{
		None,        // tous les points
		Auto,        // adapte en fonction des pixels
		FixedDensity // max n points par viewport
	};
	struct SamplingConfig
	{
		SamplingMode mode = SamplingMode::Auto;
		float maxPointsPerPixel = 1.0f;  // densité max (Auto/Fixed)
		int   minPointsPerSegment = 1;     // sécurité

		// éventuellement : type de décimation
		// enum class Strategy { MinMax, FirstLast, OHLCCompress, ... };
		// Strategy strategy = Strategy::MinMax;
	};
*/


class WChartScaleTransform {
public:
	enum class AxisDirection {
		left_to_right,
		right_to_left,
		bot_to_top,
		top_to_bot
	};

	class AxisTransform {
		float worldStart;
		float worldEnd;
		float viewportStart;
		float viewportEnd;
	public:
		AxisTransform(float wStart, float wEnd, float vStart, float vEnd)
			: worldStart(wStart), worldEnd(wEnd), viewportStart(vStart), viewportEnd(vEnd) {}
		AxisTransform() : AxisTransform(0, 1, 0, 1) {}

		virtual float getWorldStart() const { return worldStart; }
		virtual float getWorldEnd() const { return worldEnd; }
		float getWorldSize() const { return worldEnd - worldStart; }
		virtual float getViewportStart() const { return viewportStart; }
		virtual float getViewportEnd() const { return viewportEnd; }
		float getViewportSize() const { return viewportEnd - viewportStart; }
		float getZoomLevel() const { return getViewportSize() / getWorldSize(); }

		virtual AxisTransform& setWorldStart(float value) { worldStart = value; return *this; }
		virtual AxisTransform& setWorldEnd(float value) { worldEnd = value; return *this; }
		virtual AxisTransform& setViewportStart(float value) { viewportStart = value; return *this; }
		virtual AxisTransform& setViewportEnd(float value) { viewportEnd = value; return *this; }
		void setZoomLevel(float newZoom, float pivot = 0.5f)
		{
			float worldSize = getWorldSize();
			float newViewportSize = worldSize * newZoom;
			float currentCenter = viewportStart + getViewportSize() * pivot;

			viewportStart = currentCenter - newViewportSize * pivot;
			viewportEnd = viewportStart + newViewportSize;
		}
		void zoomIn(float zoomStep = 0.1f, float pivot = 0.5f) {
			const float zoom = getZoomLevel();
			float nextZoom = zoom + zoomStep;
			nextZoom = std::clamp(nextZoom, 0.0f, 1.0f);
			if (nextZoom != zoom)
				setZoomLevel(nextZoom, pivot);
		}
		void zoomOut(float zoomStep = 0.1f, float pivot = 0.5f) {
			zoomIn(-zoomStep, pivot);
		}

		float worldToViewport(float k) const {
			return k - viewportStart;
		}
		float viewportToWorld(float k) const {
			return viewportStart + k;
		}
	};

	class UnitTransform {
		AxisTransform& axisT;
		float worldStart, worldEnd;
	public:
		UnitTransform(AxisTransform& axisT) : axisT(axisT) {}

		virtual float getWorldStart() const { return worldStart; }
		virtual float getWorldEnd() const { return worldEnd; }
		float getWorldSize() const { return worldEnd - worldStart; }
		virtual float getViewportStart() const { return axisWorldToUnitWorld(axisT.getViewportStart()); }
		virtual float getViewportEnd() const { return axisWorldToUnitWorld(axisT.getViewportEnd()); }
		float getViewportSize() const { return getViewportEnd() - getViewportStart(); }
		float getZoomLevel() const { return getViewportSize() / getWorldSize(); }

		virtual UnitTransform& setWorldStart(float value) { worldStart = value; return *this; }
		virtual UnitTransform& setWorldEnd(float value) { worldEnd = value; return *this; }
		virtual UnitTransform& setViewportStart(float value) { axisT.setViewportStart(unitWorldToAxisWorld(value)); return *this; }
		virtual UnitTransform& setViewportEnd(float value) { axisT.setViewportEnd(unitWorldToAxisWorld(value)); return *this; }
		virtual UnitTransform& setZoomLevel(float newZoom, float pivot = 0.5f) { axisT.setZoomLevel(newZoom, pivot); return *this; }
		virtual void zoomIn(float zoomStep = 0.1f, float pivot = 0.5f) { axisT.zoomIn(zoomStep, pivot); }
		virtual void zoomOut(float zoomStep = 0.1f, float pivot = 0.5f) { axisT.zoomOut(zoomStep, pivot); }

		virtual float axisWorldToUnitWorld(float k) const {
			return mapValue(k, axisT.getWorldStart(), axisT.getWorldEnd(), worldStart, worldEnd);
		}
		virtual float unitWorldToAxisWorld(float k) const {
			return mapValue(k, worldStart, worldEnd, axisT.getWorldStart(), axisT.getWorldEnd());
		}
		virtual float axisViewportToUnitViewport(float k) {
			return mapValue(
				k,
				axisT.getViewportStart(),
				axisT.getViewportEnd(),
				worldStart,
				worldEnd
			);
		}
		virtual float unitViewportToAxisViewport(float k) {
			return mapValue(
				k,
				worldStart,
				worldEnd,
				axisT.getViewportStart(),
				axisT.getViewportEnd()
			);
		}

	private:
		template<typename T>
		static T mapValue(T x, T in_min, T in_max, T out_min, T out_max) {
			return (x - in_min) * (out_max - out_min) / (in_max - in_min) + out_min;
		}
	};

	WChartScaleTransform()
	: xUnit(xWorld)
	, yUnit(yWorld) {
		
	}


	AxisTransform xWorld;
	UnitTransform xUnit;
	AxisDirection xDir = AxisDirection::left_to_right;
	AxisTransform yWorld;
	UnitTransform yUnit;
	AxisDirection yDir = AxisDirection::bot_to_top;
};



