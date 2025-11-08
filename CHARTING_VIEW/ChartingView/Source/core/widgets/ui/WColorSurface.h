/*
  ==============================================================================

	WColorSurface.h
	Created: 8 Nov 2025 1:06:00am
	Author:  Jonathan

  ==============================================================================
*/

#pragma once
#include "BaseComponent.h"

class WColorSurface : public BaseComponent {
public:

	WColorSurface(Colour c) : _colour(c) {
		getPreferredSize().setPreferredSize(100, 100, false);
	}

	void paint(Graphics& g) override {
		g.fillAll(_colour);
	}

private:
	Colour _colour;
};
