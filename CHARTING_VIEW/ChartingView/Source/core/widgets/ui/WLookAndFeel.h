/*
  ==============================================================================

	WLookAndFeel.h
	Created: 8 Nov 2025 12:00:30am
	Author:  Jonathan

  ==============================================================================
*/

#pragma once
#include "JuceHeader.h"


class WLookAndFeel : public LookAndFeel_V4 {
public:

	inline static Colour bgColour = Colours::black.brighter(0.1f);
	inline static Colour bgWidgetColour = Colours::black.brighter(0.15f);

	inline static float widgetCorner = 6;

	WLookAndFeel() {
		setColour(juce::ResizableWindow::backgroundColourId, bgColour);
	}
};


